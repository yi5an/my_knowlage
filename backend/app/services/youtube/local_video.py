"""Download YouTube videos to local/NAS storage for in-app playback."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, TaskJob, Video
from app.services.structured_output import StructuredOutputClient
from app.services.task_worker import JobHandler

logger = logging.getLogger(__name__)

YOUTUBE_LOCAL_VIDEO_JOB_TYPE = "youtube_local_video_download"


@dataclass(frozen=True)
class LocalVideoDownloadResult:
    path: str
    size: int


class YtDlpLocalVideoDownloader:
    """Small wrapper around yt-dlp for downloading browser-playable MP4 files."""

    def download(
        self,
        *,
        video_id: str,
        target_root: Path,
        proxy_url: str | None,
    ) -> LocalVideoDownloadResult:
        target_dir = target_root / video_id
        temp_dir = target_root / f".{video_id}.{uuid4().hex}.tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        target_root.mkdir(parents=True, exist_ok=True)
        url = f"https://www.youtube.com/watch?v={video_id}"
        output_template = str(temp_dir / "%(id)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--merge-output-format",
            "mp4",
            "-f",
            "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
            "-o",
            output_template,
            url,
        ]
        if proxy_url:
            cmd[1:1] = ["--proxy", proxy_url]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60 * 60)
            mp4_files = sorted(temp_dir.glob("*.mp4"))
            if not mp4_files:
                raise RuntimeError("yt-dlp completed but did not produce an mp4 file")
            if target_dir.exists():
                shutil.rmtree(target_dir)
            temp_dir.rename(target_dir)
            final_path = target_dir / mp4_files[0].name
            return LocalVideoDownloadResult(
                path=str(final_path),
                size=final_path.stat().st_size,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(f"yt-dlp failed: {detail}") from exc
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)


def enqueue_local_video_download_job(session: Session, video: Video) -> TaskJob:
    existing = session.scalar(
        select(TaskJob).where(
            TaskJob.workspace_id == video.workspace_id,
            TaskJob.job_type == YOUTUBE_LOCAL_VIDEO_JOB_TYPE,
            TaskJob.target_type == "video",
            TaskJob.target_id == video.id,
            TaskJob.status.in_(("pending", "running")),
        )
    )
    if existing is not None:
        return existing

    job = TaskJob(
        id=f"job_yt_video_download_{uuid4().hex}",
        workspace_id=video.workspace_id,
        job_type=YOUTUBE_LOCAL_VIDEO_JOB_TYPE,
        target_type="video",
        target_id=video.id,
        status="pending",
        progress=0,
        input={"video_id": video.video_id},
    )
    video.local_video_status = "queued"
    video.local_video_error = None
    session.add(job)
    session.commit()
    return job


def enqueue_missing_local_video_download_jobs(
    session: Session,
    *,
    workspace_id: str | None = None,
    limit: int = 100,
) -> int:
    """Queue local downloads for completed YouTube summaries missing video files."""
    conditions = [
        Video.platform == "youtube",
        Video.local_video_status == "not_downloaded",
        Document.source_type == "youtube",
        Document.parse_status == "completed",
    ]
    if workspace_id is not None:
        conditions.append(Video.workspace_id == workspace_id)
    videos = list(
        session.scalars(
            select(Video)
            .join(Document, Document.video_id == Video.id)
            .where(*conditions)
            .order_by(Video.published_at.desc().nullslast(), Video.created_at.desc())
            .limit(limit)
        )
    )
    count = 0
    for video in videos:
        enqueue_local_video_download_job(session, video)
        count += 1
    return count


class YouTubeLocalVideoDownloadHandler(JobHandler):
    def __init__(self, downloader: YtDlpLocalVideoDownloader | None = None) -> None:
        self.downloader = downloader or YtDlpLocalVideoDownloader()

    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        from app.core.config import get_settings

        video = session.get(Video, job.target_id) if job.target_id else None
        if video is None:
            raise ValueError(f"video not found for task job {job.id}")

        settings = get_settings()
        video.local_video_status = "downloading"
        video.local_video_error = None
        session.commit()

        try:
            result = self.downloader.download(
                video_id=video.video_id,
                target_root=Path(settings.youtube_local_video_dir),
                proxy_url=settings.youtube_proxy_url,
            )
        except Exception as exc:
            video.local_video_status = "failed"
            video.local_video_error = str(exc)
            session.commit()
            raise

        video.local_video_status = "downloaded"
        video.local_video_path = result.path
        video.local_video_size = result.size
        video.local_video_downloaded_at = datetime.now(UTC)
        video.local_video_error = None
        session.commit()
        logger.info("downloaded local YouTube video %s -> %s", video.video_id, result.path)
        return {
            "video_id": video.video_id,
            "path": result.path,
            "size": result.size,
            "status": "downloaded",
        }


def register() -> None:
    from app.services import task_worker

    task_worker._HANDLERS[YOUTUBE_LOCAL_VIDEO_JOB_TYPE] = YouTubeLocalVideoDownloadHandler()
