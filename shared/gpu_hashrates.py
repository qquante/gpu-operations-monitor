"""
GPU hashrate database for Pearl (TMAD algorithm).
Sources: PEARL_MINING_COMPLETE_GUIDE.md + confirmed pool dashboards.

Kernel rule:
  RTX 40xx and below  → Akoya (more efficient kernel)
  RTX 50xx            → AlphaPool (Blackwell kernel)
  H100 / H200         → Akoya (confirmed 594 TH/s in logs)
"""

GPU_DATABASE: dict[str, dict] = {
    # ── RTX 30xx ──────────────────────────────────────────────────────────────
    "RTX 3060 Ti": {
        "ths": 45.0,
        "ths_min": 40.0,
        "ths_max": 50.0,
        "kernel": "akoya",
        "difficulty": 131072,
        "supported": True,
        "notes": "AlphaPool confirmed",
    },
    "RTX 3070": {
        "ths": 55.0,
        "ths_min": 50.0,
        "ths_max": 60.0,
        "kernel": "akoya",
        "difficulty": 131072,
        "supported": True,
        "notes": "AlphaPool confirmed",
    },
    "RTX 3070 Ti": {
        "ths": 58.0,
        "ths_min": 55.0,
        "ths_max": 62.0,
        "kernel": "akoya",
        "difficulty": 131072,
        "supported": True,
        "notes": "Estimated",
    },
    "RTX 3080": {
        "ths": 85.0,
        "ths_min": 85.0,
        "ths_max": 85.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "Akoya/AlphaPool confirmed",
    },
    "RTX 3080 Ti": {
        "ths": 88.0,
        "ths_min": 85.0,
        "ths_max": 90.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "Estimated, similar to 3080",
    },
    "RTX 3090": {
        "ths": 90.0,
        "ths_min": 90.0,
        "ths_max": 90.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "AlphaPool confirmed 90 TH/s",
    },
    "RTX 3090 Ti": {
        "ths": 93.0,
        "ths_min": 90.0,
        "ths_max": 95.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "Estimated",
    },
    # ── RTX 40xx ──────────────────────────────────────────────────────────────
    "RTX 4070": {
        "ths": 100.0,
        "ths_min": 90.0,
        "ths_max": 110.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "Estimated",
    },
    "RTX 4070 Ti": {
        "ths": 125.0,
        "ths_min": 110.0,
        "ths_max": 135.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "Estimated",
    },
    "RTX 4080": {
        "ths": 155.0,
        "ths_min": 140.0,
        "ths_max": 165.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "Estimated",
    },
    "RTX 4090": {
        "ths": 195.0,
        "ths_min": 190.0,
        "ths_max": 195.0,
        "kernel": "akoya",
        "difficulty": 524288,
        "supported": True,
        "notes": "Akoya OFFICIAL 195 TH/s — melhor que AlphaPool (150-160)",
    },
    # ── RTX 50xx ──────────────────────────────────────────────────────────────
    "RTX 5070 Ti": {
        "ths": 120.0,
        "ths_min": 110.0,
        "ths_max": 130.0,
        "kernel": "alphamine",
        "difficulty": 524288,
        "supported": True,
        "notes": "AlphaPool Blackwell kernel",
    },
    "RTX 5080": {
        "ths": 167.0,
        "ths_min": 165.0,
        "ths_max": 170.0,
        "kernel": "alphamine",
        "difficulty": 524288,
        "supported": True,
        "notes": "AlphaPool Blackwell kernel confirmed",
    },
    "RTX 5090": {
        "ths": 310.0,
        "ths_min": 300.0,
        "ths_max": 320.0,
        "kernel": "alphamine",
        "difficulty": 1048576,
        "supported": True,
        "notes": "AlphaPool 300-320 TH/s — Akoya só faz 250",
    },
    # ── Workstation / Datacenter ───────────────────────────────────────────────
    "RTX A4000": {
        "ths": 72.0,
        "ths_min": 70.0,
        "ths_max": 75.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "Akoya estimado, Ampere",
    },
    "RTX A5000": {
        "ths": 80.0,
        "ths_min": 75.0,
        "ths_max": 85.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "Estimado, Ampere",
    },
    "RTX A6000": {
        "ths": 90.0,
        "ths_min": 85.0,
        "ths_max": 95.0,
        "kernel": "akoya",
        "difficulty": 262144,
        "supported": True,
        "notes": "Estimado, similar RTX 3090",
    },
    "H100 SXM": {
        "ths": 594.0,
        "ths_min": 594.0,
        "ths_max": 615.0,
        "kernel": "akoya",
        "difficulty": 1048576,
        "supported": True,
        "notes": "Akoya CONFIRMADO logs: 594.63 TH/s, gpuUtilPct=100",
    },
    "H100 PCIe": {
        "ths": 594.0,
        "ths_min": 580.0,
        "ths_max": 610.0,
        "kernel": "akoya",
        "difficulty": 1048576,
        "supported": True,
        "notes": "Akoya confirmado",
    },
    "H100 NVL": {
        "ths": 610.0,
        "ths_min": 594.0,
        "ths_max": 620.0,
        "kernel": "akoya",
        "difficulty": 1048576,
        "supported": True,
        "notes": "Similar ao H100 SXM",
    },
    "H200": {
        "ths": 635.0,
        "ths_min": 620.0,
        "ths_max": 650.0,
        "kernel": "akoya",
        "difficulty": 1048576,
        "supported": True,
        "notes": "Estimado, Akoya/AlphaPool",
    },
    # ── Baixo hash para o preço — tecnicamente funciona, raramente lucrativo ──
    "A100 SXM": {
        "ths": 50.0,
        "ths_min": 45.0,
        "ths_max": 55.0,
        "kernel": "akoya",
        "difficulty": 131072,
        "supported": True,
        "low_value": True,
        "notes": "Ampere datacenter, difficulty 131k → ~50 TH/s. Caro demais na maioria dos provedores.",
    },
    "A100 PCIe": {
        "ths": 50.0,
        "ths_min": 45.0,
        "ths_max": 55.0,
        "kernel": "akoya",
        "difficulty": 131072,
        "supported": True,
        "low_value": True,
        "notes": "Igual A100 SXM",
    },
    # ── BLACKLIST ──────────────────────────────────────────────────────────────
    "CMP 90HX": {
        "ths": 0.035,
        "supported": False,
        "reason": "PCIe 1.0 x4 = 0.25 GB/s — gargalo total. INÚTIL para Pearl.",
    },
    "CMP 70HX": {
        "ths": 0.01,
        "supported": False,
        "reason": "PCIe bandwidth insuficiente.",
    },
    "RTX 2070": {"ths": 0, "supported": False, "reason": "Turing — kernels pendentes."},
    "RTX 2080": {"ths": 0, "supported": False, "reason": "Turing — kernels pendentes."},
    "RTX 2080 Ti": {"ths": 0, "supported": False, "reason": "Turing — kernels pendentes."},
    "T4": {"ths": 0, "supported": False, "reason": "Turing — kernels pendentes."},
}

# Pool fees (fraction, e.g. 0.05 = 5%)
POOL_FEES: dict[str, float] = {
    "pearlhash": 0.03,
    "alphamine": 0.06,   # 5% pool + 1% dev fee
    "akoya": 0.05,
    "mineprl": 0.044,
}

# ── GPU name normalization ─────────────────────────────────────────────────────
# Maps raw platform names → our GPU_DATABASE keys. None = not supported.
_GPU_NAME_MAP: dict[str, str | None] = {
    # Akoya dashboard
    "NVIDIA H100 80GB HBM3": "H100 SXM",
    "NVIDIA GeForce RTX 3060 Ti": "RTX 3060 Ti",
    "NVIDIA GeForce RTX 3070": "RTX 3070",
    "NVIDIA GeForce RTX 3070 Ti": "RTX 3070 Ti",
    "NVIDIA GeForce RTX 3080 Ti": "RTX 3080 Ti",
    "NVIDIA GeForce RTX 3090 Ti": "RTX 3090 Ti",
    "NVIDIA GeForce RTX 4070 Ti": "RTX 4070 Ti",
    "NVIDIA GeForce RTX 4080": "RTX 4080",
    "NVIDIA GeForce RTX 5080": "RTX 5080",
    "NVIDIA GeForce RTX 3090": "RTX 3090",
    "NVIDIA GeForce RTX 3080": "RTX 3080",
    "NVIDIA GeForce RTX 3080 ×18": "RTX 3080",
    "NVIDIA GeForce RTX 4090": "RTX 4090",
    "NVIDIA GeForce RTX 5090": "RTX 5090",
    # RunPod
    "NVIDIA H100 SXM": "H100 SXM",
    "NVIDIA H100 PCIe": "H100 PCIe",
    "NVIDIA H100 NVL": "H100 NVL",
    "NVIDIA H200 SXM": "H200",
    "NVIDIA RTX A4000": "RTX A4000",
    "NVIDIA RTX A5000": "RTX A5000",
    "NVIDIA RTX A6000": "RTX A6000",
    "NVIDIA RTX 5090": "RTX 5090",
    "NVIDIA RTX 4090": "RTX 4090",
    "NVIDIA A100-SXM4-80GB": "A100 SXM",
    "NVIDIA A100 PCIe": "A100 PCIe",
    "A100 PCIE": "A100 PCIe",
    # TensorDock
    "RTX A4000": "RTX A4000",
    "RTX 3090": "RTX 3090",
    "RTX 4090": "RTX 4090",
    "RTX 5090": "RTX 5090",
    "Tesla V100 16GB": None,
    "Tesla V100 32GB": None,
    "RTX 5000 ADA": None,
    "A100 SXM4": "A100 SXM",
    # Clore — gpu_array field names (no "NVIDIA" prefix, no count)
    "GeForce RTX 3060 Ti": "RTX 3060 Ti",
    "GeForce RTX 3070": "RTX 3070",
    "GeForce RTX 3070 Ti": "RTX 3070 Ti",
    "GeForce RTX 3080": "RTX 3080",
    "GeForce RTX 3080 Ti": "RTX 3080 Ti",
    "GeForce RTX 3090": "RTX 3090",
    "GeForce RTX 3090 Ti": "RTX 3090 Ti",
    "GeForce RTX 4070": "RTX 4070",
    "GeForce RTX 4070 SUPER": "RTX 4070",
    "GeForce RTX 4070 Ti": "RTX 4070 Ti",
    "GeForce RTX 4070 Ti SUPER": "RTX 4070 Ti",
    "GeForce RTX 4080": "RTX 4080",
    "GeForce RTX 4090": "RTX 4090",
    "GeForce RTX 5070 Ti": "RTX 5070 Ti",
    "GeForce RTX 5080": "RTX 5080",
    "GeForce RTX 5090": "RTX 5090",
    "RTX 4070 SUPER": "RTX 4070",
    "RTX 4070 Ti SUPER": "RTX 4070 Ti",
    "RTX 4070S Ti": "RTX 4070 Ti",
    "RTX 4080S": "RTX 4080",
    "RTX 4000Ada": None,
    "RTX PRO 4500": None,
    "RTX PRO 6000 S": None,
    "RTX PRO 6000 WS": None,
    "B200": None,
    "B300 SXM6 AC": None,
    "L4": None,
    "L40": None,
    "RTX 3060": None,
    "RTX 3060 laptop": None,
    "RTX 5060 Ti": None,
    "RTX 5070": None,
    "RTX PRO 4000": None,
    "RTX PRO 5000": None,
    "CMP 90HX": "CMP 90HX",
    # Laptop GPUs — mobile variants have 40-50% lower TDP and are not profitable
    "RTX 3060 Laptop GPU": None,
    "RTX 3070 Laptop GPU": None,
    "RTX 3080 Laptop GPU": None,
    "RTX 4060 Laptop GPU": None,
    "RTX 4070 Laptop GPU": None,
    "RTX 4080 Laptop GPU": None,
    "RTX 4090 Laptop GPU": None,
}


def normalize_gpu_name(raw_name: object) -> str | None:
    """Return our standard GPU key for a raw platform name, or None if unknown."""
    if not isinstance(raw_name, str) or not raw_name:
        return None

    if raw_name in _GPU_NAME_MAP:
        return _GPU_NAME_MAP[raw_name]
    if raw_name in GPU_DATABASE:
        return raw_name
    # Fuzzy: check if any key is a substring of raw_name (case-insensitive)
    upper = raw_name.upper()
    for key in GPU_DATABASE:
        if key.upper() in upper:
            return key
    return None


def get_gpu(name: object) -> dict | None:
    """Get GPU data dict by raw or normalized name. Returns None if not found."""
    key = normalize_gpu_name(name)
    return GPU_DATABASE.get(key) if key else None


def is_supported(name: str) -> bool:
    data = get_gpu(name)
    return bool(data and data.get("supported", False))
