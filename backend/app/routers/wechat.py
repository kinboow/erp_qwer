from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
import base64
import ctypes
import httpx
import logging
import platform
import struct
from ctypes import wintypes
from typing import List, Optional, Any
from pydantic import BaseModel

from app.database import get_db
from app.models import WechatInstance, WechatRoomListener, User
from app.dependencies import get_current_user
from app.schemas import (
    WechatInstanceCreate,
    WechatInstanceUpdate,
    WechatInstanceResponse,
    WechatListenerUpdate,
    WechatBatchUpdateListeners,
    Response
)

logger = logging.getLogger(__name__)

router = APIRouter()


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class RGBQUAD(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", ctypes.c_ubyte),
        ("rgbGreen", ctypes.c_ubyte),
        ("rgbRed", ctypes.c_ubyte),
        ("rgbReserved", ctypes.c_ubyte),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", RGBQUAD * 1),
    ]


def _normalize_instance_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _find_window_by_pid(pid: int) -> dict:
    if platform.system() != "Windows":
        raise RuntimeError("当前服务仅支持在 Windows 环境下按 PID 截图")

    user32 = ctypes.windll.user32
    candidates = []
    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, lparam):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value != pid:
            return True
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return True
        title_length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
        candidates.append({
            "hwnd": hwnd,
            "title": title_buffer.value,
            "width": width,
            "height": height,
            "area": width * height,
        })
        return True

    if not user32.EnumWindows(enum_windows_proc(callback), 0):
        raise RuntimeError("枚举进程窗口失败")

    if not candidates:
        raise RuntimeError("未找到该 PID 对应的可见窗口")

    candidates.sort(key=lambda item: item["area"], reverse=True)
    return candidates[0]


def _capture_window_data_url(pid: int) -> dict:
    window_info = _find_window_by_pid(pid)
    hwnd = window_info["hwnd"]
    width = window_info["width"]
    height = window_info["height"]

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    if hasattr(user32, "SetProcessDPIAware"):
        user32.SetProcessDPIAware()
    pw_render_full_content = 0x00000002
    srccopy = 0x00CC0020
    dib_rgb_colors = 0

    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        raise RuntimeError("获取窗口 DC 失败")

    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    if not mem_dc:
        user32.ReleaseDC(hwnd, hwnd_dc)
        raise RuntimeError("创建兼容 DC 失败")

    bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
    if not bitmap:
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)
        raise RuntimeError("创建位图失败")

    old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
    try:
        painted = user32.PrintWindow(hwnd, mem_dc, pw_render_full_content)
        if not painted:
            painted = user32.PrintWindow(hwnd, mem_dc, 0)
        if not painted:
            copied = gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, srccopy)
            if not copied:
                raise RuntimeError("抓取窗口图像失败")

        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = width
        bitmap_info.bmiHeader.biHeight = height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = 0
        bitmap_info.bmiHeader.biSizeImage = width * height * 4

        pixel_buffer = ctypes.create_string_buffer(bitmap_info.bmiHeader.biSizeImage)
        dib_result = gdi32.GetDIBits(mem_dc, bitmap, 0, height, pixel_buffer, ctypes.byref(bitmap_info), dib_rgb_colors)
        if not dib_result:
            raise RuntimeError("读取位图数据失败")

        file_header = struct.pack(
            "<HIHHI",
            0x4D42,
            14 + ctypes.sizeof(BITMAPINFOHEADER) + len(pixel_buffer.raw),
            0,
            0,
            14 + ctypes.sizeof(BITMAPINFOHEADER),
        )
        info_header = struct.pack(
            "<IIIHHIIIIII",
            ctypes.sizeof(BITMAPINFOHEADER),
            width,
            height,
            1,
            32,
            0,
            len(pixel_buffer.raw),
            0,
            0,
            0,
            0,
        )
        bmp_bytes = file_header + info_header + pixel_buffer.raw
        encoded = base64.b64encode(bmp_bytes).decode("ascii")
        return {
            "pid": pid,
            "title": window_info["title"],
            "width": width,
            "height": height,
            "image": f"data:image/bmp;base64,{encoded}",
        }
    finally:
        gdi32.SelectObject(mem_dc, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)


def _extract_room_list(raw_data: Any) -> list:
    if isinstance(raw_data, list):
        return raw_data
    if isinstance(raw_data, dict):
        for key in ["room_list", "list", "items", "records", "rooms", "data"]:
            value = raw_data.get(key)
            if isinstance(value, list):
                return value
    return []


def _normalize_room_item(room: Any) -> Optional[dict]:
    if isinstance(room, dict):
        room_id = room.get("room_id") or room.get("roomId") or room.get("id") or room.get("conversation_id") or room.get("room_conversation_id")
        room_name = room.get("room_name") or room.get("roomName") or room.get("name") or room.get("nickname") or room.get("nick_name") or room_id or "未命名群聊"
        if not room_id:
            return None
        return {"room_id": room_id, "room_name": room_name}
    if isinstance(room, str):
        room_id = room.strip()
        if not room_id:
            return None
        return {"room_id": room_id, "room_name": room_id}
    return None


# 统一响应格式处理
def json_response(code=0, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


# -----------------
# 实例管理
# -----------------

@router.get("/instances", summary="获取实例列表")
def get_instances(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    instances = db.query(WechatInstance).order_by(WechatInstance.created_at.desc()).all()
    # 将模型转为字典并包含 snake_case -> camelCase 的必要转换供前端使用
    result = []
    for inst in instances:
        result.append({
            "id": inst.id,
            "wxid": inst.wxid,
            "name": inst.name,
            "status": inst.status,
            "api_base_url": inst.api_base_url,
            "api_key": inst.api_key,
            "created_at": inst.created_at,
        })
    return json_response(data=result)


@router.post("/instances", summary="添加实例")
def create_instance(
    data: WechatInstanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 检查wxid是否已存在
    existing = db.query(WechatInstance).filter(WechatInstance.wxid == data.wxid).first()
    if existing:
        return json_response(code=-1, message="该企业微信实例ID已存在")

    db_instance = WechatInstance(
        wxid=data.wxid,
        name=data.name,
        api_base_url=data.api_base_url,
        api_key=data.api_key
    )
    db.add(db_instance)
    db.commit()
    db.refresh(db_instance)

    return json_response(data={
        "id": db_instance.id,
        "wxid": db_instance.wxid,
        "name": db_instance.name,
        "apiBaseUrl": db_instance.api_base_url,
        "apiKey": db_instance.api_key
    })


@router.put("/instances/{instance_id}", summary="更新实例")
def update_instance(
    instance_id: int,
    data: WechatInstanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_instance = db.query(WechatInstance).filter(WechatInstance.id == instance_id).first()
    if not db_instance:
        return json_response(code=-1, message="实例不存在")

    if data.name is not None:
        db_instance.name = data.name
    if data.api_base_url is not None:
        db_instance.api_base_url = data.api_base_url
    if data.api_key is not None:
        db_instance.api_key = data.api_key
    if data.status is not None:
        db_instance.status = data.status

    db.commit()
    return json_response(message="更新成功")


@router.delete("/instances/{instance_id}", summary="删除实例")
def delete_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_instance = db.query(WechatInstance).filter(WechatInstance.id == instance_id).first()
    if not db_instance:
        return json_response(code=-1, message="实例不存在")

    db.delete(db_instance)
    db.commit()
    return json_response(message="删除成功")


# -----------------
# 群聊管理 (调API)
# -----------------

def _build_headers(instance: WechatInstance) -> dict:
    """构建请求头"""
    headers = {}
    if instance.api_key:
        headers["X-API-Key"] = instance.api_key
    return headers


async def get_rooms_from_api(instance: WechatInstance) -> list:
    """内部方法：调用企业微信API获取群聊"""
    headers = _build_headers(instance)
    url = f"{instance.api_base_url}/api/{instance.wxid}/rooms/get"
    all_rooms = []
    page_num = 1
    page_size = 100

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            while True:
                logger.warning("[wechat rooms] request instance_id=%s wxid=%s url=%s page_num=%s page_size=%s", instance.id, instance.wxid, url, page_num, page_size)
                resp = await client.post(url, json={"page_num": page_num, "page_size": page_size}, headers=headers)
                resp.raise_for_status()

                data = resp.json()
                if not isinstance(data, dict):
                    logger.warning(
                        "[wechat rooms] non-dict response instance_id=%s response_type=%s response_preview=%s",
                        instance.id,
                        type(data).__name__,
                        str(data)[:500],
                    )
                    if isinstance(data, list):
                        return data
                    return all_rooms

                raw_message = data.get("msg") or data.get("message")
                raw_payload = data.get("data")
                logger.warning(
                    "[wechat rooms] response instance_id=%s code=%s message=%s data_type=%s data_keys=%s",
                    instance.id,
                    data.get("code"),
                    raw_message,
                    type(raw_payload).__name__,
                    list(raw_payload.keys()) if isinstance(raw_payload, dict) else None,
                )
                if data.get("code") != 0:
                    raise Exception(raw_message or "获取群聊列表失败")

                page_rooms = _extract_room_list(raw_payload if raw_payload is not None else [])
                logger.warning("[wechat rooms] parsed instance_id=%s page_num=%s count=%s", instance.id, page_num, len(page_rooms))
                all_rooms.extend(page_rooms)

                if len(page_rooms) < page_size:
                    break

                page_num += 1

            return all_rooms
    except httpx.HTTPError as e:
        logger.exception("[wechat rooms] http error instance_id=%s wxid=%s", instance.id, instance.wxid)
        raise Exception(f"调用企业微信API失败: {str(e)}")
    except Exception:
        logger.exception("[wechat rooms] unexpected error instance_id=%s wxid=%s", instance.id, instance.wxid)
        raise


async def get_self_info_from_api(instance: WechatInstance) -> dict:
    """内部方法：调用企业微信API获取当前登录账号信息"""
    headers = _build_headers(instance)
    url = f"{instance.api_base_url}/api/{instance.wxid}/self/info"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={}, headers=headers)
            resp.raise_for_status()

            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {})
            else:
                raise Exception(data.get("msg", "获取登录信息失败"))
    except httpx.HTTPError as e:
        raise Exception(f"调用企业微信API失败: {str(e)}")

@router.get("/instances/{instance_id}/status", summary="检测实例登录状态")
async def check_instance_status(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    instance = db.query(WechatInstance).filter(WechatInstance.id == instance_id).first()
    if not instance:
        return json_response(code=-1, message="实例不存在")

    try:
        info = await get_self_info_from_api(instance)
        # 更新数据库状态为在线
        instance.status = 1
        db.commit()
        return json_response(data={
            "online": True,
            "wxid": instance.wxid,
            "account_info": info
        })
    except Exception as e:
        # 更新数据库状态为离线
        instance.status = 0
        db.commit()
        return json_response(data={
            "online": False,
            "wxid": instance.wxid,
            "error": str(e)
        })


@router.get("/instances/{instance_id}/rooms", summary="获取群聊列表")
async def get_room_list(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    instance = db.query(WechatInstance).filter(WechatInstance.id == instance_id).first()
    if not instance:
        return json_response(code=-1, message="实例不存在")

    try:
        rooms = await get_rooms_from_api(instance)
        return json_response(data=rooms)
    except Exception as e:
        return json_response(code=-1, message=str(e))

@router.post("/instances/{instance_id}/sync-rooms", summary="同步群聊")
async def sync_rooms(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    instance = db.query(WechatInstance).filter(WechatInstance.id == instance_id).first()
    if not instance:
        return json_response(code=-1, message="实例不存在")

    try:
        rooms = await get_rooms_from_api(instance)

        synced_count = 0
        new_count = 0

        for room in rooms:
            normalized_room = _normalize_room_item(room)
            if not normalized_room:
                continue

            room_id = normalized_room["room_id"]
            room_name = normalized_room["room_name"]


            existing = db.query(WechatRoomListener).filter(
                WechatRoomListener.instance_id == instance_id,
                WechatRoomListener.room_id == room_id
            ).first()

            if existing:
                existing.room_name = room_name
                synced_count += 1
            else:
                new_listener = WechatRoomListener(
                    instance_id=instance_id,
                    room_id=room_id,
                    room_name=room_name,
                    is_enabled=0  # 默认不启用
                )
                db.add(new_listener)
                new_count += 1

        db.commit()

        return json_response(data={
            "total": len(rooms),
            "synced": synced_count,
            "new": new_count
        })
    except Exception as e:
        return json_response(code=-1, message=str(e))

# -----------------
# 监听配置管理
# -----------------

@router.get("/listeners", summary="获取监听配置列表")
def get_listeners(
    instanceId: Optional[int] = None,
    isEnabled: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(
        WechatRoomListener,
        WechatInstance.name.label("instance_name"),
        WechatInstance.wxid
    ).outerjoin(WechatInstance, WechatRoomListener.instance_id == WechatInstance.id)

    if instanceId is not None:
        query = query.filter(WechatRoomListener.instance_id == instanceId)

    if isEnabled is not None:
        query = query.filter(WechatRoomListener.is_enabled == isEnabled)

    if keyword:
        search_term = f"%{keyword}%"
        query = query.filter(or_(
            WechatRoomListener.room_name.like(search_term),
            WechatRoomListener.room_id.like(search_term)
        ))

    total = query.count()

    offset = (page - 1) * pageSize
    items = query.order_by(WechatRoomListener.updated_at.desc()).offset(offset).limit(pageSize).all()

    result_list = []
    for listener, instance_name, wxid in items:
        result_list.append({
            "id": listener.id,
            "instance_id": listener.instance_id,
            "room_id": listener.room_id,
            "room_name": listener.room_name,
            "is_enabled": listener.is_enabled,
            "description": listener.description,
            "created_at": listener.created_at,
            "updated_at": listener.updated_at,
            "instance_name": instance_name,
            "wxid": wxid
        })

    return json_response(data={
        "list": result_list,
        "total": total,
        "page": page,
        "pageSize": pageSize
    })

@router.put("/listeners/{listener_id}", summary="更新监听配置")
def update_listener(
    listener_id: int,
    data: WechatListenerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    listener = db.query(WechatRoomListener).filter(WechatRoomListener.id == listener_id).first()
    if not listener:
        return json_response(code=-1, message="监听配置不存在")

    if data.is_enabled is not None:
        listener.is_enabled = data.is_enabled
    if data.description is not None:
        listener.description = data.description

    db.commit()
    return json_response(message="更新成功")

@router.post("/listeners/batch", summary="批量更新监听状态")
def batch_update_listeners(
    data: WechatBatchUpdateListeners,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not data.roomIds:
        return json_response(message="无群聊需要更新")

    db.query(WechatRoomListener).filter(
        WechatRoomListener.instance_id == data.instanceId,
        WechatRoomListener.room_id.in_(data.roomIds)
    ).update({WechatRoomListener.is_enabled: data.isEnabled}, synchronize_session=False)

    db.commit()
    return json_response(message="批量更新成功")


# -----------------
# 代理接口（供前端配置页测试连通性）
# -----------------

class ProxyReq(BaseModel):
    api_base_url: str
    api_key: Optional[str] = None

@router.post("/proxy/health", summary="代理测试连接")
async def proxy_health(
    data: ProxyReq,
    current_user: User = Depends(get_current_user)
):
    headers = {}
    if data.api_key:
        headers["X-API-Key"] = data.api_key

    base = data.api_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{base}/api/health", headers=headers)
            resp.raise_for_status()
            return json_response(data=resp.json())
    except Exception as e:
        return json_response(code=-1, message=f"连接失败: {str(e)}")

class ProxyStartReq(BaseModel):
    api_base_url: str
    api_key: Optional[str] = None
    force_new: bool = False

@router.post("/proxy/start", summary="代理智能启动企业微信")
async def proxy_start(
    data: ProxyStartReq,
    current_user: User = Depends(get_current_user)
):
    headers = {}
    if data.api_key:
        headers["X-API-Key"] = data.api_key

    base = data.api_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base}/api/wechat/start",
                json={"force_new": data.force_new},
                headers=headers
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                return json_response(data=result.get("data"))
            else:
                return json_response(code=-1, message=result.get("msg", "启动失败"))
    except Exception as e:
        return json_response(code=-1, message=f"启动企业微信失败: {str(e)}")


class ProxyWaitLoginReq(BaseModel):
    api_base_url: str
    api_key: Optional[str] = None
    wxid: str
    timeout: Optional[float] = None

@router.post("/proxy/wait_login", summary="代理等待登录获取二维码")
async def proxy_wait_login(
    data: ProxyWaitLoginReq,
    current_user: User = Depends(get_current_user)
):
    headers = {}
    if data.api_key:
        headers["X-API-Key"] = data.api_key

    base = data.api_base_url.rstrip("/")
    body = {}
    if data.timeout is not None:
        body["timeout"] = data.timeout
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base}/api/{data.wxid}/wait_login",
                json=body,
                headers=headers
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                return json_response(data=result.get("data"))
            else:
                return json_response(code=-1, message=result.get("msg", "获取登录信息失败"))
    except Exception as e:
        return json_response(code=-1, message=f"等待登录失败: {str(e)}")

class ProxyRefreshQrReq(BaseModel):
    api_base_url: str
    api_key: Optional[str] = None
    wxid: str

@router.post("/proxy/refresh_qrcode", summary="代理刷新登录二维码")
async def proxy_refresh_qrcode(
    data: ProxyRefreshQrReq,
    current_user: User = Depends(get_current_user)
):
    headers = {}
    if data.api_key:
        headers["X-API-Key"] = data.api_key

    base = data.api_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{base}/api/{data.wxid}/refresh_qrcode",
                json={},
                headers=headers
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                return json_response(data=result.get("data"))
            else:
                return json_response(code=-1, message=result.get("msg", "刷新二维码失败"))
    except Exception as e:
        return json_response(code=-1, message=f"刷新二维码失败: {str(e)}")


class ProxyInstanceScreenshotReq(ProxyReq):
    pid: Optional[int] = None
    wxid: Optional[str] = None
    client_id: Optional[str] = None


async def _fetch_proxy_instances(api_base_url: str, api_key: Optional[str]) -> list:
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    base = api_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{base}/api/wechat/overview",
            json={"only_attached": False},
            headers=headers
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") != 0:
            raise RuntimeError(result.get("msg", "获取概览失败"))
        raw_data = result.get("data", {})
        if isinstance(raw_data, dict):
            return raw_data.get("instances", [])
        if isinstance(raw_data, list):
            return raw_data
        return []

def _resolve_instance_pid(instances: list, data: ProxyInstanceScreenshotReq) -> Optional[int]:
    target_wxid = _normalize_instance_value(data.wxid)
    target_client_id = _normalize_instance_value(data.client_id)
    target_pid = _normalize_instance_value(data.pid)

    for inst in instances:
        if target_wxid and _normalize_instance_value(inst.get("wxid")) == target_wxid:
            resolved_pid = inst.get("pid")
            return int(resolved_pid) if resolved_pid else None

    for inst in instances:
        if target_client_id and _normalize_instance_value(inst.get("client_id")) == target_client_id:
            resolved_pid = inst.get("pid")
            return int(resolved_pid) if resolved_pid else None

    for inst in instances:
        if target_pid and _normalize_instance_value(inst.get("pid")) == target_pid:
            resolved_pid = inst.get("pid")
            return int(resolved_pid) if resolved_pid else None

    return int(data.pid) if data.pid else None

@router.post("/proxy/overview", summary="代理获取实例概览")
async def proxy_overview(
    data: ProxyReq,
    current_user: User = Depends(get_current_user)
):
    try:
        instances_list = await _fetch_proxy_instances(data.api_base_url, data.api_key)
        return json_response(data=instances_list)
    except Exception as e:
        return json_response(code=-1, message=f"获取实例列表失败: {str(e)}")

class ProxyKillProcessReq(BaseModel):
    pid: int

@router.post("/proxy/kill_process", summary="强制结束指定 PID 的进程")
async def proxy_kill_process(
    data: ProxyKillProcessReq,
    current_user: User = Depends(get_current_user)
):
    import os
    import signal
    try:
        os.kill(data.pid, signal.SIGTERM)
        return json_response(data={"pid": data.pid, "killed": True})
    except ProcessLookupError:
        return json_response(data={"pid": data.pid, "killed": False}, message="进程不存在")
    except PermissionError:
        return json_response(code=-1, message="没有权限结束该进程")
    except Exception as e:
        return json_response(code=-1, message=f"结束进程失败: {str(e)}")

@router.post("/proxy/login_window_screenshot", summary="代理获取实例登录窗口截图")
async def proxy_login_window_screenshot(
    data: ProxyInstanceScreenshotReq,
    current_user: User = Depends(get_current_user)
):
    try:
        instances = await _fetch_proxy_instances(data.api_base_url, data.api_key)
        pid = _resolve_instance_pid(instances, data)
        if not pid:
            return json_response(code=-1, message="未获取到该实例的 PID")
        screenshot = _capture_window_data_url(pid)
        return json_response(data=screenshot)
    except Exception as e:
        return json_response(code=-1, message=f"获取实例登录窗口截图失败: {str(e)}")
