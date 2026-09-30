import json
from pathlib import Path

def test_lawd_cd_exists_and_valid():
    lawd_path = Path("src/constants/lawd_cd.json")
    assert lawd_path.exists(), "src/constants/lawd_cd.json does not exist"
    with open(lawd_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) >= 200, f"Expected at least 200 LAWD codes, got {len(data)}"
    assert "11110" in data, "11110 (서울 종로구) must be in lawd_cd.json"
    assert "41111" in data, "41111 (경기 수원시 장안구) must be in lawd_cd.json"

def test_config_files_exist():
    assert Path("pyproject.toml").exists(), "pyproject.toml must exist"
    assert Path("requirements.txt").exists(), "requirements.txt must exist"
    assert Path(".gitignore").exists(), ".gitignore must exist"
    assert Path(".env.example").exists(), ".env.example must exist"
