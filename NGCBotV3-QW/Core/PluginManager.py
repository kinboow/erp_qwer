# -*- coding: utf-8 -*-

import sys
import importlib.util
from pathlib import Path
from typing import Dict, Any
from loguru import logger
import tomlkit
from Core.EventDispatcher import dispatcher


class PluginManager:
    """插件管理器"""

    def __init__(self, pluginsDir: str = "Plugins"):
        self.pluginsDir = Path(pluginsDir)
        self.loadedPlugins: Dict[str, Any] = {}

    async def loadAllPlugins(self):
        """加载所有插件"""
        if not self.pluginsDir.exists():
            self.pluginsDir.mkdir(parents=True)
            logger.warning(f"插件目录不存在，已创建: {self.pluginsDir}")
            return

        logger.info("开始加载所有插件...")
        loadCount = 0

        for pluginDir in self.pluginsDir.iterdir():
            if not pluginDir.is_dir() or pluginDir.name.startswith('_'):
                continue

            if pluginDir.name in self.loadedPlugins:
                continue

            if await self.loadPlugin(pluginDir.name):
                loadCount += 1

        logger.success(f"插件加载完成，成功加载 {loadCount} 个插件")

    async def loadPlugin(self, pluginName: str) -> bool:
        """加载单个插件"""
        pluginDir = self.pluginsDir / pluginName

        if not pluginDir.exists() or not pluginDir.is_dir():
            logger.error(f"插件目录不存在: {pluginName}")
            return False

        if pluginName in self.loadedPlugins:
            logger.warning(f"插件 {pluginName} 已经加载")
            return False

        mainFile = pluginDir / "main.py"
        configFile = pluginDir / "config.toml"

        if not mainFile.exists():
            logger.error(f"插件 {pluginName} 缺少 main.py 文件")
            return False

        try:
            # 加载配置
            config = {}
            if configFile.exists():
                with open(configFile, 'r', encoding='utf-8') as f:
                    config = tomlkit.load(f)
                logger.debug(f"插件 {pluginName} 配置加载成功: {dict(config)}")
            else:
                logger.debug(f"插件 {pluginName} 没有配置文件")

            # 检查插件是否启用
            if not config.get('enabled', True):
                logger.info(f"插件 {pluginName} 已禁用")
                return False

            # 动态加载插件模块
            moduleName = f"plugins.{pluginName}"
            spec = importlib.util.spec_from_file_location(moduleName, mainFile)
            module = importlib.util.module_from_spec(spec)

            sys.modules[moduleName] = module

            # 执行模块（此时会创建 pluginConfig = {} 变量）
            spec.loader.exec_module(module)

            # 在模块执行后注入配置（覆盖模块中的空字典）
            module.pluginConfig = config

            # 调用插件的初始化函数
            if hasattr(module, 'onLoad'):
                import asyncio
                if asyncio.iscoroutinefunction(module.onLoad):
                    await module.onLoad()
                else:
                    module.onLoad()

            # 保存插件信息
            self.loadedPlugins[pluginName] = {
                'module': module,
                'config': config,
                'path': pluginDir,
                'moduleName': moduleName
            }

            logger.success(f"插件加载成功: {pluginName}")
            return True

        except Exception as e:
            logger.error(f"加载插件 {pluginName} 失败: {e}", exc_info=True)
            return False

    async def unloadPlugin(self, pluginName: str) -> bool:
        """卸载单个插件"""
        if pluginName not in self.loadedPlugins:
            logger.warning(f"插件 {pluginName} 未加载")
            return False

        try:
            pluginInfo = self.loadedPlugins[pluginName]
            module = pluginInfo['module']

            # 调用插件的卸载函数
            if hasattr(module, 'onUnload'):
                import asyncio
                if asyncio.iscoroutinefunction(module.onUnload):
                    await module.onUnload()
                else:
                    module.onUnload()

            # 注销该插件的所有事件处理器
            dispatcher.unregisterModule(module)

            # 从sys.modules中移除模块
            moduleName = pluginInfo['moduleName']
            if moduleName in sys.modules:
                del sys.modules[moduleName]

            del self.loadedPlugins[pluginName]

            logger.success(f"插件卸载成功: {pluginName}")
            return True

        except Exception as e:
            logger.error(f"卸载插件 {pluginName} 失败: {e}", exc_info=True)
            return False

    async def unloadAllPlugins(self):
        """卸载所有插件"""
        logger.info("开始卸载所有插件...")
        pluginNames = list(self.loadedPlugins.keys())

        for pluginName in pluginNames:
            await self.unloadPlugin(pluginName)

    async def reloadAllPlugins(self):
        """重载所有已加载的插件"""
        logger.info("开始重载所有插件...")
        pluginNames = list(self.loadedPlugins.keys())
        successCount = 0
        failCount = 0

        for pluginName in pluginNames:
            # 先卸载
            await self.unloadPlugin(pluginName)
            # 再加载
            if await self.loadPlugin(pluginName):
                successCount += 1
            else:
                failCount += 1

        logger.success(f"插件重载完成，成功: {successCount}, 失败: {failCount}")
        return successCount, failCount

    def getAllPlugins(self):
        """获取所有插件（包括未加载的）"""
        allPlugins = []

        if not self.pluginsDir.exists():
            return allPlugins

        for pluginDir in self.pluginsDir.iterdir():
            if not pluginDir.is_dir() or pluginDir.name.startswith('_'):
                continue

            pluginInfo = {
                'name': pluginDir.name,
                'displayName': pluginDir.name,
                'loaded': pluginDir.name in self.loadedPlugins,
                'enabled': True,
                'path': pluginDir
            }

            # 尝试读取配置获取中文名
            configFile = pluginDir / "config.toml"
            if configFile.exists():
                try:
                    with open(configFile, 'r', encoding='utf-8') as f:
                        config = tomlkit.load(f)
                        pluginInfo['displayName'] = config.get('name', pluginDir.name)
                        pluginInfo['enabled'] = config.get('enabled', True)
                        pluginInfo['version'] = config.get('version', 'unknown')
                        pluginInfo['author'] = config.get('author', 'unknown')
                        pluginInfo['description'] = config.get('description', '')
                except Exception as e:
                    logger.debug(f"读取插件 {pluginDir.name} 配置失败: {e}")

            allPlugins.append(pluginInfo)

        return allPlugins

    def getPluginDisplayName(self, pluginName: str) -> str:
        """获取插件的显示名称（中文名）"""
        # 如果已加载，从loadedPlugins中获取
        if pluginName in self.loadedPlugins:
            config = self.loadedPlugins[pluginName].get('config', {})
            return config.get('name', pluginName)

        # 如果未加载，尝试读取配置文件
        pluginDir = self.pluginsDir / pluginName
        configFile = pluginDir / "config.toml"

        if configFile.exists():
            try:
                with open(configFile, 'r', encoding='utf-8') as f:
                    config = tomlkit.load(f)
                    return config.get('name', pluginName)
            except Exception:
                pass

        return pluginName

    async def dispatchEvent(self, eventType: int, wxType, data: dict):
        """
        分发事件

        参数:
            eventType: 事件类型（数字）
            wxType: 微信消息类型（支持数字或字符串）
            data: 回调数据
        """
        await dispatcher.dispatch(eventType, wxType, data)


# 全局插件管理器实例
pluginManager = PluginManager()
