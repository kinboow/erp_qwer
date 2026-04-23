# -*- coding: utf-8 -*-

import tomlkit
from pathlib import Path


def getConfigPath():
    """获取配置文件路径"""
    return Path(__file__).parent / 'config.toml'


def getConfigData():
    """获取全局配置数据"""
    configPath = getConfigPath()
    with open(configPath, 'r', encoding='utf-8') as f:
        return tomlkit.load(f)


def getNGCConfig():
    """获取NGCBotApi配置"""
    return getConfigData().get('NGCBOTAPI', {})


def getCallbackConfig():
    """获取回调服务器配置"""
    return getConfigData().get('CALLBACK', {})
