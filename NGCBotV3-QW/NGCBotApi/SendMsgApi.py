from .InterFaceApi import sendPost
from loguru import logger

class SendMsgApi:
    def __init__(self):
        pass

    async def sendText(self, robotId: str, receive: str, content: str):
        """
        发送文本消息
        API: POST /api/{wxid}/send/text

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            content (str): 消息内容

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'content': content,
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/text')
            return jsonData
        except Exception as e:
            logger.error(f'发送文本消息出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送文本消息出现错误: {e}', 'data': {}}

    async def sendAtText(self, robotId: str, receive: str, content: str, atList: list):
        """
        发送群@消息
        API: POST /api/{wxid}/send/room_at

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 群的conversation_id
            content (str): 群消息内容
            atList (list): @的列表、@所有人传 ['0']

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'content': content,
                'at_list': atList
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/room_at')
            return jsonData
        except Exception as e:
            logger.error(f'发送@文本消息出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送@文本消息出现错误: {e}', 'data': {}}

    async def sendFriendCard(self, robotId: str, receive: str, wxId: str):
        """
        发送名片
        API: POST /api/{wxid}/send/card

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            wxId (str): 被分享用户的user_id

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'share_user_id': wxId
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/card')
            return jsonData
        except Exception as e:
            logger.error(f'发送好友名片出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送好友名片出现错误: {e}', 'data': {}}

    async def sendLinkCard(self, robotId: str, receive: str, title: str, desc: str, url: str, imageUrl: str):
        """
        发送卡片消息
        API: POST /api/{wxid}/send/link_card

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            title (str): 标题
            desc (str): 描述
            url (str): 链接
            imageUrl (str): 图片URL

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'title': title,
                'desc': desc,
                'url': url,
                'image_url': imageUrl
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/link_card')
            return jsonData
        except Exception as e:
            logger.error(f'发送链接卡片出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送链接卡片出现错误: {e}', 'data': {}}

    async def sendImage(self, robotId: str, receive: str, imagePath: str):
        """
        发送图片
        API: POST /api/{wxid}/send/image

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            imagePath (str): 图片路径或base64

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'file': imagePath
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/image')
            return jsonData
        except Exception as e:
            logger.error(f'发送图片出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送图片出现错误: {e}', 'data': {}}

    async def sendFile(self, robotId: str, receive: str, filePath: str):
        """
        发送文件
        API: POST /api/{wxid}/send/file

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            filePath (str): 文件路径

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'file': filePath
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/file')
            return jsonData
        except Exception as e:
            logger.error(f'发送文件出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送文件出现错误: {e}', 'data': {}}

    async def sendVideo(self, robotId: str, receive: str, videoPath: str):
        """
        发送视频
        API: POST /api/{wxid}/send/video

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            videoPath (str): 视频文件路径

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'file': videoPath
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/video')
            return jsonData
        except Exception as e:
            logger.error(f'发送视频文件出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送视频文件出现错误: {e}', 'data': {}}

    async def sendGif(self, robotId: str, receive: str, gifPath: str):
        """
        发送动图
        API: POST /api/{wxid}/send/gif

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            gifPath (str): GIF文件路径

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'file': gifPath
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/gif')
            return jsonData
        except Exception as e:
            logger.error(f'发送Gif文件出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送Gif文件出现错误: {e}', 'data': {}}

    async def sendMiniapp(self, robotId: str, receive: str, username: str, appid: str, title: str, 
                          pagePath: str, fileId: str, aesKey: str, md5: str, size: int):
        """
        发送小程序
        API: POST /api/{wxid}/send/miniapp

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            username (str): 小程序用户名
            appid (str): 小程序APPID
            title (str): 小程序标题
            pagePath (str): 小程序页面路径
            fileId (str): 文件ID
            aesKey (str): AES密钥
            md5 (str): MD5值
            size (int): 大小

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'username': username,
                'appid': appid,
                'title': title,
                'page_path': pagePath,
                'file_id': fileId,
                'aes_key': aesKey,
                'md5': md5,
                'size': size
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/miniapp')
            return jsonData
        except Exception as e:
            logger.error(f'发送小程序出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送小程序出现错误: {e}', 'data': {}}
    
    async def sendFinderVideo(self, robotId: str, receive: str, avatar: str, coverUrl: str, 
                             desc: str, feedType: int, nickname: str, thumbUrl: str, url: str, extras: str = ''):
        """
        发送视频号
        API: POST /api/{wxid}/send/finder_video

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            avatar (str): 头像URL
            coverUrl (str): 封面URL
            desc (str): 描述
            feedType (int): Feed类型
            nickname (str): 昵称
            thumbUrl (str): 缩略图URL
            url (str): 视频URL
            extras (str): 额外信息，默认为空

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'avatar': avatar,
                'cover_url': coverUrl,
                'desc': desc,
                'feed_type': feedType,
                'nickname': nickname,
                'thumb_url': thumbUrl,
                'url': url,
                'extras': extras
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/finder_video')
            return jsonData
        except Exception as e:
            logger.error(f'发送视频号出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送视频号出现错误: {e}', 'data': {}}
    
    async def sendFinderLive(self, robotId: str, receive: str, avatar: str, coverUrl: str, desc: str, 
                            feedType: int, nickname: str, objectId: str, objectNonceId: str, 
                            thumbUrl: str, url: str, extras: str = ''):
        """
        发送视频号直播
        API: POST /api/{wxid}/send/finder_live

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的conversation_id
            avatar (str): 头像URL
            coverUrl (str): 封面URL
            desc (str): 描述
            feedType (int): Feed类型
            nickname (str): 昵称
            objectId (str): 对象ID
            objectNonceId (str): 对象Nonce ID
            thumbUrl (str): 缩略图URL
            url (str): 直播URL
            extras (str): 额外信息，默认为空

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': receive,
                'avatar': avatar,
                'cover_url': coverUrl,
                'desc': desc,
                'extras': extras,
                'feed_type': feedType,
                'nickname': nickname,
                'object_id': objectId,
                'object_nonce_id': objectNonceId,
                'thumb_url': thumbUrl,
                'url': url
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='send/finder_live')
            return jsonData
        except Exception as e:
            logger.error(f'发送视频号直播出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'发送视频号直播出现错误: {e}', 'data': {}}

    async def revokeMsg(self, robotId: str, clientMsgId: int, createTime: int, wxId: str, newMsgId: str):
        """
        撤回消息

        Args:
            clientMsgId (int): 消息ID
            createTime (int): 消息创建时间
            wxId (str): 消息发送者的wxId
            newMsgId (str): 新的消息ID

        Returns:
            {}
        """
        try:
            raise NotImplementedError('暂不支持撤回消息')
            data = {
                'client_msgid': clientMsgId,
                'create_time': createTime,
                'to_wxid': wxId,
                'new_msgid': newMsgId
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='revoke_msg')
            return jsonData
        except Exception as e:
            logger.error(f'撤回消息出现错误, 错误信息: {e}')
            return {'code': -1, 'message': f'撤回消息出现错误, 错误信息: {e}', 'data': {}}

    async def forwardMsg(self, robotId: str, receive: str, msgId: str):
        """
        转发消息

        Args:
            robotId (str): 机器人的微信ID
            receive (str): 接收者的wxId
            msgId (str): 消息ID

        Returns:
            {}
        """
        try:
            data = {
                'msgid': msgId,
                'to_wxid': receive
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='forward_msg')
            return jsonData
        except Exception as e:
            logger.error(f'转发消息出现错误, 错误信息: {e}')
            return {'code': -1, 'message': f'转发消息出现错误, 错误信息: {e}', 'data': {}}


if __name__ == '__main__':
    import asyncio
    XML = """
    <msg><appmsg appid="" sdkver="0"><title>群聊的聊天记录</title><des>NGCBot: 11
NGCBot: 1
NGCBot: 发个XML给我
NGCBot: @大鹏\u2005你发这个试试</des><action></action><type>19</type><showtype>0</showtype><soundtype>0</soundtype><mediatagname></mediatagname><messageext></messageext><messageaction></messageaction><content></content><contentattr>0</contentattr><url></url><lowurl></lowurl><dataurl></dataurl><lowdataurl></lowdataurl><songalbumurl></songalbumurl><songlyric></songlyric><template_id></template_id><appattach><totallen>0</totallen><attachid></attachid><emoticonmd5></emoticonmd5><fileext></fileext><aeskey></aeskey></appattach><extinfo></extinfo><sourceusername></sourceusername><sourcedisplayname></sourcedisplayname><thumburl></thumburl><md5></md5><statextstr></statextstr><recorditem><![CDATA[<recordinfo><fromscene>0</fromscene><favcreatetime>1762084748</favcreatetime><isChatRoom>0</isChatRoom><title>群聊的聊天记录</title><desc>NGCBot: 11
NGCBot: 1
NGCBot: 发个XML给我
NGCBot: @大鹏\u2005你发这个试试</desc><datalist count="4"><dataitem datatype="1" dataid="28fe68900abd7d7ce337e418ebc45d5d" htmlid="28fe68900abd7d7ce337e418ebc45d5d"><sourcename>NGCBot</sourcename><sourceheadurl>https://wx.qlogo.cn/mmhead/ver_1/ib8gMISVt0WNwSYaJII8iaqAicQ6Ao1O6ticbehWIDe1M0lR3v0RQfX9aGwP3Zt36NvoWSwK6sYecVIr5xATQI0D2hN61ChYpKR2EDHNxzYfPw9YKovanKtAia1Sj6YJSuLYiajq7S6afjHiaVaThfhQ0HAZA/132</sourceheadurl><sourcetime>2025-11-02 19:46</sourcetime><datadesc>11</datadesc><srcMsgLocalid>1</srcMsgLocalid><srcMsgCreateTime>1762083969</srcMsgCreateTime><fromnewmsgid>724500293556650928</fromnewmsgid><dataitemsource><hashusername>41b7dc700234524128390a285f948640106922e853e106e8c0dfbae1384506dd</hashusername></dataitemsource></dataitem><dataitem datatype="1" dataid="6a9d3f49a6089831276eb20e21676959" htmlid="6a9d3f49a6089831276eb20e21676959"><sourcename>NGCBot</sourcename><sourceheadurl>https://wx.qlogo.cn/mmhead/ver_1/ib8gMISVt0WNwSYaJII8iaqAicQ6Ao1O6ticbehWIDe1M0lR3v0RQfX9aGwP3Zt36NvoWSwK6sYecVIr5xATQI0D2hN61ChYpKR2EDHNxzYfPw9YKovanKtAia1Sj6YJSuLYiajq7S6afjHiaVaThfhQ0HAZA/132</sourceheadurl><sourcetime>2025-11-02 19:47</sourcetime><datadesc>1</datadesc><srcMsgLocalid>2</srcMsgLocalid><srcMsgCreateTime>1762084041</srcMsgCreateTime><fromnewmsgid>3726282613688232116</fromnewmsgid><dataitemsource><hashusername>41b7dc700234524128390a285f948640106922e853e106e8c0dfbae1384506dd</hashusername></dataitemsource></dataitem><dataitem datatype="1" dataid="5eb7949e619059db441df89dc5ecd0ad" htmlid="5eb7949e619059db441df89dc5ecd0ad"><sourcename>NGCBot</sourcename><sourceheadurl>https://wx.qlogo.cn/mmhead/ver_1/ib8gMISVt0WNwSYaJII8iaqAicQ6Ao1O6ticbehWIDe1M0lR3v0RQfX9aGwP3Zt36NvoWSwK6sYecVIr5xATQI0D2hN61ChYpKR2EDHNxzYfPw9YKovanKtAia1Sj6YJSuLYiajq7S6afjHiaVaThfhQ0HAZA/132</sourceheadurl><sourcetime>2025-11-02 19:50</sourcetime><datadesc>发个XML给我</datadesc><srcMsgLocalid>3</srcMsgLocalid><srcMsgCreateTime>1762084226</srcMsgCreateTime><fromnewmsgid>9131880438524169069</fromnewmsgid><dataitemsource><hashusername>41b7dc700234524128390a285f948640106922e853e106e8c0dfbae1384506dd</hashusername></dataitemsource></dataitem><dataitem datatype="1" dataid="1f0bb54209cd29611cb9e1bf3cf2b4c8" htmlid="1f0bb54209cd29611cb9e1bf3cf2b4c8"><sourcename>NGCBot</sourcename><sourceheadurl>https://wx.qlogo.cn/mmhead/ver_1/ib8gMISVt0WNwSYaJII8iaqAicQ6Ao1O6ticbehWIDe1M0lR3v0RQfX9aGwP3Zt36NvoWSwK6sYecVIr5xATQI0D2hN61ChYpKR2EDHNxzYfPw9YKovanKtAia1Sj6YJSuLYiajq7S6afjHiaVaThfhQ0HAZA/132</sourceheadurl><sourcetime>2025-11-02 19:59</sourcetime><datadesc>@大鹏\u2005你发这个试试</datadesc><srcMsgLocalid>7</srcMsgLocalid><srcMsgCreateTime>1762084742</srcMsgCreateTime><fromnewmsgid>4918277454994292239</fromnewmsgid><dataitemsource><hashusername>41b7dc700234524128390a285f948640106922e853e106e8c0dfbae1384506dd</hashusername></dataitemsource></dataitem></datalist></recordinfo>]]></recorditem></appmsg><fromusername>wxid_iemewc0wrqyk22</fromusername><appinfo><version>0</version><appname></appname><isforceupdate>0</isforceupdate></appinfo></msg>
    """.strip()
    # result = asyncio.run(SendMsgApi().sendText(robotId='wxid_iemewc0wrqyk22', receive='wxid_7bizfilssbwi22', content='测试'))
    result = asyncio.run(SendMsgApi().sendAtText(robotId='wxid_iemewc0wrqyk22', receive='56198206776@chatroom', content='你好', atList=['notify@all']))
    # result = asyncio.run(SendMsgApi().sendFriendCard(robotId='wxid_iemewc0wrqyk22', receive='wxid_7bizfilssbwi22', wxId='wxid_7bizfilssbwi22'))
    # result = asyncio.run(SendMsgApi().sendLinkCard(robotId='wxid_iemewc0wrqyk22', receive='wxid_7bizfilssbwi22', title='测试', desc='测试', url='http://www.baidu.com', imageUrl='https://img.jbzj.com/file_images/Illustrator/201702/2017020411591786.png'))
    # result = asyncio.run(SendMsgApi().sendImage(robotId='wxid_iemewc0wrqyk22', receive='wxid_7bizfilssbwi22', imagePath='C:/Users/Administrator/Downloads/test.png'))
    # result = asyncio.run(SendMsgApi().sendFile(robotId='wxid_iemewc0wrqyk22', receive='wxid_7bizfilssbwi22', filePath='C:/Users/Administrator/Downloads/test.docx'))
    # result = asyncio.run(SendMsgApi().sendVideo(robotId='wxid_iemewc0wrqyk22', receive='wxid_7bizfilssbwi22', videoPath='C:/Users/Administrator/Downloads/test.mp4'))
    # result = asyncio.run(SendMsgApi().sendGif(robotId='wxid_iemewc0wrqyk22', receive='wxid_7bizfilssbwi22', gifPath='C:/Users/Administrator/Downloads/test.gif'))
    # result = asyncio.run(SendMsgApi().sendXml(robotId='wxid_iemewc0wrqyk22', receive='wxid_7bizfilssbwi22', xml=XML))
    result = asyncio.run(SendMsgApi().revokeMsg(robotId='wxid_iemewc0wrqyk22', clientMsgId=4294590401873128902, createTime=1762679132, wxId='wxid_7bizfilssbwi22', newMsgId='448922'))
    # result = asyncio.run(SendMsgApi().forwardMsg(receive='wxid_7bizfilssbwi22', msgId='8388950634332672827'))
    print(result)