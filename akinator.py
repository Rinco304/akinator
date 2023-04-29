from .utils import Switch, Akinator
from datetime import datetime, timedelta
from asyncio import sleep

from hoshino import Service
from hoshino.typing import CQEvent
from hoshino.typing import MessageSegment as Seg
from hoshino.util import FreqLimiter, DailyNumberLimiter

import aiohttp
aki = Akinator()

help_text="""
[网络天才] 开始游戏
[结束网络天才] 结束游戏
※每人每天最多开始三次游戏
回答问题：
[是/是的/对/有/在/会/yes/y/1]
[否/不是/不对/没有/不在/不会/no/n/2]
[我不知道/不知道/不清楚/idk/3]
[可能是/也许是/或许是/应该是/大概是/4]
[可能不是/也许不是/或许不是/应该不是/大概不是/5]
[b][返回][上一个] 返回上一个问题
※若游戏中回答问题后无反应，是因为接下来的内容违反了QQ聊天规则导致被QQ阻止发送
  这种情况下可以尝试使用[返回]重新答题绕过此问题或者结束游戏
※由于api设置有查询限制，此功能不能多人(多群)一起使用(后发起游戏的群会有很高概率把先发起游戏的群的连接切断)
""".strip()

sv = Service('网络天才', help_=help_text)


yes = ['是', '是的', '对', '有', '在','yes', 'y', '1', '会']
no = ['不是','不','不对','否', '没有', '不在', 'no','n','2', '不会']
idk = ['我不知道','不知道','不清楚','idk','3']
probably = ['可能是','也许是', '或许是', '应该是', '大概是', '4']
probablyn = ['可能不是','也许不是','或许不是', '应该不是', '大概不是','5']
back = ['返回','上一个','b','B']

sw = Switch()
client_session = aiohttp.ClientSession()
_lmt = DailyNumberLimiter(3)    # 每日次数限制
all_status = 0    # 总限制
_cd = 30   #冷却时长(s)
_flmt = FreqLimiter(_cd)

@sv.on_fullmatch('网络天才')
async def akinator_start(bot, ev: CQEvent):
    global all_status
    uid = ev.user_id
    gid = ev.group_id
    if not _lmt.check(uid):
        await bot.finish(ev, '每天最多玩三次哦~您今天的次数已用完，请明天再来_(:з」∠)_', at_sender=True)
    if not _flmt.check(uid):
        await bot.finish(ev, f"您冲得太快了，有{_cd}秒冷却哦", at_sender=True)
    if all_status == 1:
        if sw.get_on_off_status(gid):
            if uid == sw.on[gid]:
                sw.timeout[gid] = datetime.now()+timedelta(seconds=30)
                await bot.finish(ev, f"您已经开始游戏啦")
            else:
                await bot.finish(ev, f"本群[CQ:at,qq={sw.on[gid]}]正在玩，请耐心等待~")
        else:
            bot.finish(ev, f"有其他群正在使用此功能，请耐心等待~")
    
    try:
        all_status = 1
        r = await aki.start_game(language='cn',client_session=client_session)
        q = r['question']
        sw.turn_on(gid, uid, r)
    except Exception as e:
        all_status = 0
        if "Cannot connect to host cn.akinator.com:443 ssl" in str(e):
            await bot.send(ev,f'服务器出问题了，一会再来玩吧\n网络连接断开，请检查网络情况')
        else:
            await bot.send(ev,f'服务器出问题了，一会再来玩吧\n{e}')
        return
    await bot.send(ev,q)
    await sleep(30)
    ct = 0
    while sw.get_on_off_status(gid):
        if datetime.now() < sw.timeout[gid]:
            if ct != sw.count[gid]:
                ct = sw.count[gid]
                sw.timeout[gid] = datetime.now()+timedelta(seconds=60)
        else:
            temp = sw.on[gid]
            await bot.send(ev, f"[CQ:at,qq={temp}] 由于超时，已为您自动结束游戏")
            all_status = 0
            sw.turn_off(gid)
            break
        await sleep(30)
    return

@sv.on_message('group')
async def answer_question(bot, ev: CQEvent):
    global all_status
    if sw.get_on_off_status(ev.group_id) is False:
        return
    uid = ev.user_id
    gid = ev.group_id
    if not(uid == int(sw.on[gid])):
        return
    
    reply = ev.message.extract_plain_text()
    try:
        if reply in yes:
            r = await aki.answer('0',sw.aki[gid])
        elif reply in no:
            r = await aki.answer('1',sw.aki[gid])
        elif reply in idk:
            r = await aki.answer('2',sw.aki[gid])
        elif reply in probably:
            r = await aki.answer('3',sw.aki[gid])
        elif reply in probablyn:
            r = await aki.answer('4',sw.aki[gid])
        elif reply in back:
            r = await aki.back(sw.aki[gid])
        else:
            return
        q = r['question']
        sw.count_plus(gid, r)
    except Exception as e:
        all_status = 0
        if "Cannot connect to host cn.akinator.com:443 ssl" in str(e):
            await bot.send(ev,f'服务器出问题了，一会再来玩吧\n网络连接断开，请检查网络情况')
        else:
            await bot.send(ev,f'服务器出问题了，一会再来玩吧\n{e}')
        sw.turn_off(gid)
        return
    
    if r['progression'] > 80:
        answer = await aki.win(sw.aki[gid])
        msg = f"是 {answer['name']} ({answer['description']})! 我猜对了么?"+Seg.image(answer['absolute_picture_path'])
        await bot.send(ev,msg)
        _flmt.start_cd(uid)
        _lmt.increase(uid)
        all_status = 0
        sw.turn_off(gid)
        return
    else:
        await bot.send(ev,q)
        

@sv.on_fullmatch('结束网络天才')
async def akinator_end(bot,ev: CQEvent):
    global all_status
    uid = ev.user_id
    gid = ev.group_id
    if sw.get_on_off_status(gid):
        if sw.on[gid] != ev.user_id:
            await bot.send(ev, '不能替别人结束游戏哦～')
            return
    _flmt.start_cd(uid)
    _lmt.increase(uid)
    all_status = 0
    sw.turn_off(gid)
    await bot.send(ev,'已结束')
