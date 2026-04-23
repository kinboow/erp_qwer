import Config.ConfigServer as Cs
import aiohttp
import json
from loguru import logger

NGCBOTConfig = Cs.getNGCConfig()

async def sendPost(data: dict, robotId: str = '', route: str = ''):
    """
    发送异步POST请求
    :param data: 请求数据
    :param robotId: 机器人微信ID
    :param route: 请求路由（新格式: send/text, contacts/internal等）
    :return: 响应JSON数据
    """
    # 新接口格式: /api/{wxid}/{route}
    api = f'http://127.0.0.1:{NGCBOTConfig.get("PORT")}/api/{robotId}/{route}'
    headers = {
        'X-API-Key': NGCBOTConfig.get('X-API-KEY'),  # 注意大小写
        'Content-Type': 'application/json; charset=utf-8'
    }
    
    # 创建连接器和超时配置
    connector = aiohttp.TCPConnector(ssl=False)
    timeout = aiohttp.ClientTimeout(total=20)
    
    try:
        logger.debug(f'发送API请求: {api}')
        logger.debug(f'请求数据: {json.dumps(data, ensure_ascii=False)}')
        
        # 使用 dumps_kwargs 参数确保中文不被转义
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, json_serialize=lambda x: json.dumps(x, ensure_ascii=False)) as session:
            async with session.post(api, json=data, headers=headers) as response:
                jsonData = await response.json()
                logger.debug(f'API响应: {json.dumps(jsonData, ensure_ascii=False)}')
                return jsonData
    except TimeoutError as e:
        logger.error(f'请求超时: {api}')
        raise e
    except Exception as e:
        logger.error(f'请求失败: {api}, 错误: {e}', exc_info=True)
        raise e

