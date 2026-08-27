import requests
import json
from pathlib import Path
from loguru import logger
from google.protobuf import descriptor_pb2
from google.protobuf import descriptor_pool

BASE_DIR = Path(__file__).resolve().parent.parent
LIQI_FILES = {"max_data.yaml": "config", "liqi.desc": "proto"}

def _auth_headers(token: str):
    headers = {"X-GitHub-Api-Version": "2022-11-28"}
    if token != "":
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _download_liqi_latest_release(token: str):
    req = requests.get(
        "https://api.github.com/repos/Avenshy/MajsoulData/releases/latest",
        timeout=10,
        headers=_auth_headers(token),
    )
    return req

def _download_max_latest_release(token: str):
    req = requests.get(
        "https://api.github.com/repos/Avenshy/MajsoulMax/releases/latest",
        timeout=10,
        headers=_auth_headers(token),
    )
    return req

def _download_liqi_assets(release: dict, token: str):
    assets = {
        item["name"]: item
        for item in release.get("assets", [])
        if item["name"] in LIQI_FILES.keys()
    }
    if len(assets) != len(LIQI_FILES.keys()):
        missing = {name for name in LIQI_FILES.keys() if name not in assets}
        raise FileNotFoundError(f"发布页缺少文件: {missing}")

    blobs = {}
    for name in LIQI_FILES.keys():
        item = assets[name]
        logger.warning(f"下载 {name} 中……")
        req = requests.get(
            item["browser_download_url"], timeout=10, headers=_auth_headers(token)
        )
        blobs[name] = req.content
        logger.success(f"下载 {name} 成功！")
    return blobs

def _generate_liqi_json():
    fds = descriptor_pb2.FileDescriptorSet()
    with open(BASE_DIR / "proto" / "liqi.desc", "rb") as f:
        fds.ParseFromString(f.read())

    pool = descriptor_pool.DescriptorPool()
    for file in fds.file:
        pool.Add(file)
    rpc_map = {}
    for file in fds.file:
        package = file.package  # lq

        for service in file.service:
            service_name = service.name  # Lobby

            for method in service.method:
                method_name = method.name

                full_method = f".{package}.{service_name}.{method_name}"

                rpc_map[full_method] = {
                    "req": method.input_type,
                    "resp": method.output_type
                }
    with open(BASE_DIR / 'proto' / 'liqi.json', 'w') as f:
        json.dump(rpc_map, f,  separators=(',', ':'),indent =None)


def update(max_version, liqi_version, token):
    req = _download_liqi_latest_release(token)
    if req.headers.get("X-RateLimit-Remaining") == "0":
        # 匿名 API 额度(60次/h)耗尽：无法确认远端版本，跳过本次检查。
        # 本地文件可能已是最新，不应误报"无法更新"。
        logger.warning("GitHub API 额度已用完，跳过 liqi 更新检查（本地版本：{}）。", liqi_version)
        logger.warning("如需手动更新：前往 https://github.com/Avenshy/MajsoulData/releases/latest 下载 "
                       "max_data.yaml 放入 ./config/、liqi.desc 放入 ./proto/（均覆盖同名文件），"
                       "并将 ./config/settings.yaml 的 liqi.liqi_version 改为最新版本号")
        return liqi_version
    
    liqi = req.json()
    new_version = liqi["tag_name"]

    if liqi_version == new_version :
        logger.success(f"liqi文件无需更新，当前版本：{new_version}")
    else:
        blobs = _download_liqi_assets(liqi, token)
        for name in LIQI_FILES:
            with open(BASE_DIR / LIQI_FILES[name] / name, "wb") as f:
                f.write(blobs[name])
        _generate_liqi_json()
        logger.success(f"liqi文件更新成功：{new_version}")
    
    req = _download_max_latest_release(token)
    if req.headers.get("X-RateLimit-Remaining") != "0":
        max = req.json()
        new_max_version = max["tag_name"]
        if max_version == new_max_version:
            logger.success(f"雀魂MAX无需更新，当前版本：{new_max_version}")
        else:
            logger.warning(f"雀魂MAX有新版本：{new_max_version}，请前往 {max['html_url']} 下载更新！")
        
    return new_version
