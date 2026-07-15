from __future__ import annotations


def default_themes() -> list[dict[str, object]]:
    return [
        {
            "name": "AI 算力",
            "theme_type": "sector",
            "keywords": ["HBM", "AI 服务器", "数据中心电力", "光模块", "先进封装"],
            "entities": [
                "NVDA",
                "NVIDIA",
                "英伟达",
                "Jensen Huang",
                "黄仁勋",
                "AMD",
                "台积电",
                "博通",
                "Marvell",
                "Arista",
                "Supermicro",
            ],
            "tickers": ["NVDA", "AMD", "TSM", "AVGO", "MRVL", "ANET", "SMCI"],
            "priority": "high",
        },
        {
            "name": "宏观",
            "theme_type": "macro",
            "keywords": ["美联储", "通胀", "就业", "财政", "美元流动性", "FOMC", "Treasury"],
            "entities": ["Federal Reserve", "BLS", "Treasury", "BEA"],
            "tickers": [],
            "priority": "high",
        },
        {
            "name": "特斯拉 / Robotaxi / 自动驾驶",
            "theme_type": "company_cluster",
            "keywords": ["Robotaxi", "FSD", "自动驾驶", "NHTSA", "Waymo", "车险"],
            "entities": ["Tesla", "Waymo", "NHTSA"],
            "tickers": ["TSLA"],
            "priority": "high",
        },
        {
            "name": "黄金 / 能源 / 军工 / 消费 / 港股科技",
            "theme_type": "asset",
            "keywords": ["黄金", "能源", "军工", "消费", "港股科技"],
            "entities": [],
            "tickers": [],
            "priority": "medium",
        },
    ]
