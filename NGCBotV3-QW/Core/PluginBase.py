# -*- coding: utf-8 -*-

from typing import Dict, Any
from loguru import logger
from NGCBotApi import NGCBotApi


class PluginBase:
    """插件基类（可选继承）"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.name = self.config.get('name', self.__class__.__name__)
        self.bot = NGCBotApi()
        logger.info(f"插件 [{self.name}] 初始化完成")

    async def onLoad(self):
        """插件加载时调用"""
        pass

    async def onUnload(self):
        """插件卸载时调用"""
        pass
