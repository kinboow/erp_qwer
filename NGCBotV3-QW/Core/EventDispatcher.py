# -*- coding: utf-8 -*-

from typing import Callable, Dict, List, Tuple, Optional, Union
from loguru import logger


class EventDispatcher:
    """事件分发器 - 支持type和wxType的组合判断"""

    def __init__(self):
        # 存储处理器：key可以是 (type,), (type, wxType), 或 (None, wxType)
        self.handlers: Dict[Tuple, List[Callable]] = {}

    def register(self, eventType: Optional[int], wxType: Optional[Union[int, str]], handler: Callable):
        """注册事件处理器"""
        key = self._makeKey(eventType, wxType)
        if key not in self.handlers:
            self.handlers[key] = []
        self.handlers[key].append(handler)
        logger.debug(f"注册事件处理器: type={eventType}, wxType={wxType}, handler={handler.__name__}")

    def unregister(self, eventType: Optional[int], wxType: Optional[Union[int, str]], handler: Callable = None):
        """注销事件处理器"""
        key = self._makeKey(eventType, wxType)
        if key not in self.handlers:
            return

        if handler is None:
            del self.handlers[key]
            logger.debug(f"注销事件类型 type={eventType}, wxType={wxType} 的所有处理器")
        else:
            if handler in self.handlers[key]:
                self.handlers[key].remove(handler)
                logger.debug(f"注销事件处理器: type={eventType}, wxType={wxType}, handler={handler.__name__}")

            if not self.handlers[key]:
                del self.handlers[key]

    def unregisterModule(self, module):
        """注销指定模块的所有事件处理器"""
        count = 0
        keysToRemove = []

        for key, handlers in self.handlers.items():
            handlersToRemove = []
            for handler in handlers:
                # 检查处理器是否属于该模块
                if hasattr(handler, '__module__') and handler.__module__ == module.__name__:
                    handlersToRemove.append(handler)
                    count += 1

            # 移除该模块的处理器
            for handler in handlersToRemove:
                handlers.remove(handler)

            # 如果该key下没有处理器了，标记删除
            if not handlers:
                keysToRemove.append(key)

        # 删除空的key
        for key in keysToRemove:
            del self.handlers[key]

        if count > 0:
            logger.info(f"注销了 {count} 个事件处理器")

        return count

    def _makeKey(self, eventType: Optional[int], wxType: Optional[Union[int, str]]) -> Tuple:
        """生成处理器的key"""
        if eventType is not None and wxType is not None:
            return (eventType, wxType)
        elif eventType is not None:
            return (eventType,)
        elif wxType is not None:
            return (None, wxType)
        else:
            raise ValueError("eventType和wxType不能同时为None")

    async def dispatch(self, eventType: int, wxType: Union[int, str], data: dict):
        """分发事件到所有注册的处理器"""
        # 查找匹配的处理器
        matchedHandlers = []

        # 1. 精确匹配 (type, wxType)
        key1 = (eventType, wxType)
        if key1 in self.handlers:
            matchedHandlers.extend(self.handlers[key1])

        # 2. 只匹配 type
        key2 = (eventType,)
        if key2 in self.handlers:
            matchedHandlers.extend(self.handlers[key2])

        # 3. 只匹配 wxType
        key3 = (None, wxType)
        if key3 in self.handlers:
            matchedHandlers.extend(self.handlers[key3])

        if not matchedHandlers:
            logger.debug(f"没有找到匹配的处理器: type={eventType}, wxType={wxType}")
            return

        logger.info(f"分发事件 type={eventType}, wxType={wxType} 到 {len(matchedHandlers)} 个处理器")

        for handler in matchedHandlers:
            try:
                await handler(data)
            except Exception as e:
                logger.error(f"处理器 {handler.__name__} 执行失败: {e}", exc_info=True)


# 全局事件分发器实例
dispatcher = EventDispatcher()


def messageHandle(type: Optional[int] = None, wxType: Optional[Union[int, str]] = None):
    """
    装饰器：注册消息处理器

    支持三种模式：
    1. @messageHandle(type=11046) - 只判断type
    2. @messageHandle(wxType=1) - 只判断wxType（支持数字）
    3. @messageHandle(wxType="text") - 只判断wxType（支持字符串）
    4. @messageHandle(type=11046, wxType=1) - 同时判断type和wxType

    参数:
        type: 事件类型（数字）
        wxType: 微信消息类型（支持数字或字符串）
    """
    if type is None and wxType is None:
        raise ValueError("type和wxType不能同时为None")

    def decorator(func: Callable):
        dispatcher.register(type, wxType, func)
        return func
    return decorator
