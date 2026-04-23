import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from loguru import logger
from NGCBotApi import NGCBotApi

bot = NGCBotApi()
pluginConfig = {}
task_handle = None

async def onLoad():
    global task_handle
    logger.info(f"[{pluginConfig.get('name', 'AINewsPush')}] 插件已加载")
    settings = pluginConfig.get('settings', {})
    logger.info(f"推送时间: {settings.get('pushHour', 10)}:{settings.get('pushMinute', 0):02d}")

    # 启动定时任务
    task_handle = asyncio.create_task(schedule_task())

async def onUnload():
    global task_handle
    if task_handle:
        task_handle.cancel()
    logger.info(f"[{pluginConfig.get('name', 'AINewsPush')}] 插件已卸载")

async def schedule_task():
    """定时任务调度"""
    while True:
        try:
            settings = pluginConfig.get('settings', {})
            push_hour = settings.get('pushHour', 10)
            push_minute = settings.get('pushMinute', 0)

            now = datetime.now()
            target_time = now.replace(hour=push_hour, minute=push_minute, second=0, microsecond=0)

            if now >= target_time:
                target_time += timedelta(days=1)

            wait_seconds = (target_time - now).total_seconds()
            logger.info(f"[AI新闻推送] 下次推送时间: {target_time}, 等待 {wait_seconds/3600:.2f} 小时")

            await asyncio.sleep(wait_seconds)
            await push_news()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"定时任务异常: {e}")
            await asyncio.sleep(3600)

async def push_news():
    """推送新闻"""
    try:
        settings = pluginConfig.get('settings', {})
        rss_url = settings.get('rssUrl', '')
        robot_wxid = settings.get('robotWxid', '')

        # 获取今日新闻
        news_items = await fetch_today_news(rss_url)

        if not news_items:
            logger.warning("没有获取到今日新闻")
            return

        # 使用AI总结新闻
        summary = await summarize_news(news_items, settings)

        if not summary:
            logger.error("AI总结新闻失败")
            return

        # 推送到群聊
        target_groups = settings.get('targetGroups', [])
        for group_id in target_groups:
            await bot.sendText(robot_wxid, group_id, summary)
            await asyncio.sleep(1)

        # 推送到个人
        target_users = settings.get('targetUsers', [])
        for user_id in target_users:
            await bot.sendText(robot_wxid, user_id, summary)
            await asyncio.sleep(1)

        logger.success(f"新闻推送完成，共推送 {len(target_groups)} 个群聊，{len(target_users)} 个用户")

    except Exception as e:
        logger.error(f"推送新闻失败: {e}")

async def fetch_today_news(rss_url: str) -> list:
    """获取今日新闻"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(rss_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    content = await response.text()
                    root = ET.fromstring(content)

                    today = datetime.now().date()
                    news_items = []

                    for item in root.findall('.//item'):
                        title = item.find('title').text if item.find('title') is not None else ''
                        link = item.find('link').text if item.find('link') is not None else ''
                        pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
                        description = item.find('description').text if item.find('description') is not None else ''

                        # 简单判断是否为今日新闻（可根据实际RSS格式调整）
                        news_items.append({
                            'title': title,
                            'link': link,
                            'description': description,
                            'pubDate': pub_date
                        })

                    # 返回前10条
                    return news_items[:10]

                logger.error(f"获取RSS失败: {response.status}")
                return []
    except Exception as e:
        logger.error(f"获取RSS新闻失败: {e}")
        return []

async def summarize_news(news_items: list, settings: dict) -> str:
    """使用AI总结新闻"""
    try:
        api_key = settings.get('apiKey', '')
        api_url = settings.get('apiUrl', '')
        model = settings.get('model', 'deepseek-chat')

        # 构建新闻内容
        news_text = "今日AI技术新闻：\n\n"
        for i, item in enumerate(news_items, 1):
            news_text += f"{i}. {item['title']}\n"
            if item.get('description'):
                news_text += f"   {item['description'][:100]}...\n"
            news_text += f"   链接: {item['link']}\n\n"

        # 调用AI总结
        messages = [
            {"role": "system", "content": "你是一个专业的AI技术新闻编辑，擅长总结和提炼技术要点。"},
            {"role": "user", "content": f"请用中文总结以下AI技术新闻，提炼出3-5个关键要点，每个要点用一句话概括，并在最后附上完整的新闻列表：\n\n{news_text}"}
        ]

        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    summary = result['choices'][0]['message']['content']
                    return f"📰 今日AI技术新闻推送\n\n{summary}"
                else:
                    logger.error(f"AI总结失败: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"AI总结新闻失败: {e}")
        return None
