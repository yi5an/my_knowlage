from tests.test_investment_themes_api import _client


def test_create_person_source_for_theme() -> None:
    client, _ = _client()
    theme = client.post(
        "/api/v1/investment/themes",
        json={"name": "宏观", "theme_type": "macro", "keywords": ["FOMC"]},
    ).json()

    created = client.post(
        "/api/v1/investment/person-sources",
        json={
            "theme_ids": [theme["id"]],
            "platform": "x",
            "handle": "@NickTimiraos",
            "display_name": "Nick Timiraos",
            "role_type": "journalist",
            "credibility": 0.85,
            "noise_level": 0.2,
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["handle"] == "NickTimiraos"
    assert body["theme_ids"] == [theme["id"]]
