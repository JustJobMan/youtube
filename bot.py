import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import googleapiclient.discovery
from datetime import datetime, timedelta
import re
import pytz
import aiohttp
import time

if os.path.exists('config.env'):
    load_dotenv('config.env')

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
FIREBASE_URL = "https://notan-cb053-default-rtdb.firebaseio.com"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

@bot.event
async def on_ready():
    print(f'봇이 로그인되었습니다: {bot.user.name} (ID: {bot.user.id})')
    print('------')

@bot.command(name='명령어')
async def help_commands(ctx):
    msg = (
        "```\n"
        "📋 사용 가능한 명령어\n"
        "──────────────────────────────\n"
        "!링크 [유튜브링크]\n"
        "  → 유튜브 라이브 방송 시작/종료/총 방송시간 조회\n\n"
        "!공지 [내용]\n"
        "  → 방송 중 운세룰렛 칸에 공지 10초 송출\n"
        "──────────────────────────────\n"
        "```"
    )
    await ctx.send(msg)

@bot.command(name='링크')
async def youtube_link(ctx, url: str):
    await ctx.send("유튜브 라이브 정보를 가져오는 중입니다. 잠시만 기다려 주세요...")

    video_id = None
    match = re.search(r'(?:v=|youtu\.be/|live/)([a-zA-Z0-9_-]{11})(?:\?|&|$)', url)
    if match:
        video_id = match.group(1)

    if not video_id:
        await ctx.send("유효한 유튜브 링크 주소를 찾을 수 없습니다. `!링크 [유튜브 라이브 링크주소]` 형식으로 입력해주세요.")
        return

    try:
        request = youtube.videos().list(
            part="liveStreamingDetails,snippet",
            id=video_id
        )
        response = request.execute()

        if not response['items']:
            await ctx.send(f"해당 ID({video_id})에 대한 유튜브 비디오 정보를 찾을 수 없습니다.")
            return

        item = response['items'][0]
        live_details = item.get('liveStreamingDetails')
        snippet = item.get('snippet')

        if not live_details:
            await ctx.send("이 비디오는 라이브 스트리밍 정보가 없는 것 같습니다. 라이브 스트림만 지원합니다.")
            return

        title = snippet.get('title', '제목 없음')
        channel_title = snippet.get('channelTitle', '채널 정보 없음')

        start_time_str = live_details.get('actualStartTime')
        end_time_str = live_details.get('actualEndTime')

        korea_tz = pytz.timezone('Asia/Seoul')

        start_dt_kst = None
        end_dt_kst = None
        total_duration = None

        if start_time_str:
            start_dt_utc = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            start_dt_kst = start_dt_utc.astimezone(korea_tz)

        if end_time_str:
            end_dt_utc = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            end_dt_kst = end_dt_utc.astimezone(korea_tz)

        if start_dt_kst and end_dt_kst:
            total_duration = end_dt_kst - start_dt_kst
        elif start_dt_kst and not end_dt_kst:
            current_dt_utc = datetime.now(pytz.utc)
            current_dt_kst = current_dt_utc.astimezone(korea_tz)
            total_duration = current_dt_kst - start_dt_kst

        response_message = f"**{title}** (채널: {channel_title})\n"
        response_message += "```\n"

        if start_dt_kst:
            response_message += f"{start_dt_kst.strftime('%m/%d')}\n"
            response_message += f"방송 시작 {start_dt_kst.strftime('%H시 %M분 %S초 (%m/%d)')}\n"
        else:
            response_message += "방송 시작: 정보 없음\n"

        if end_dt_kst:
            response_message += f"방송 종료 {end_dt_kst.strftime('%H시 %M분 %S초 (%m/%d)')}\n"
        elif start_dt_kst and not end_dt_kst:
            response_message += "방송 종료: 현재 라이브 중\n"
        else:
            response_message += "방송 종료: 정보 없음\n"

        response_message += "\n"

        if total_duration:
            total_seconds = int(total_duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            response_message += f"총 방송 시간 {hours}시간 {minutes}분 {seconds}초\n"
        else:
            response_message += "총 방송 시간: 계산 불가 (라이브 중이거나 정보 부족)\n"

        response_message += "```"
        await ctx.send(response_message)

    except googleapiclient.errors.HttpError as e:
        if e.resp.status == 403:
            await ctx.send("유튜브 API 할당량 초과 또는 API 키에 문제가 있습니다. 잠시 후 다시 시도하거나 API 키를 확인해주세요.")
        elif e.resp.status == 400:
            await ctx.send("유튜브 API 요청이 잘못되었습니다. 비디오 ID가 유효한지 확인해주세요.")
        else:
            await ctx.send(f"유튜브 API 호출 중 오류가 발생했습니다: {e}")
        print(f"YouTube API Error: {e}")
    except Exception as e:
        await ctx.send(f"오류가 발생했습니다: {e}")
        print(f"Error: {e}")

@bot.command(name='공지')
async def announce(ctx, *, message: str):
    try:
        async with aiohttp.ClientSession() as session:
            data = {
                "message": message,
                "timestamp": int(time.time() * 1000)
            }
            async with session.put(
                f"{FIREBASE_URL}/announcement.json",
                json=data
            ) as resp:
                if resp.status == 200:
                    await ctx.send(f"📢 공지 전송 완료: **{message}**")
                else:
                    await ctx.send(f"공지 전송 실패 (상태코드: {resp.status})")
    except Exception as e:
        await ctx.send(f"공지 전송 중 오류가 발생했습니다: {e}")
        print(f"Announce Error: {e}")

if __name__ == '__main__':
    if not DISCORD_BOT_TOKEN:
        print("오류: DISCORD_BOT_TOKEN이 설정되지 않았습니다. 환경 변수를 확인해주세요.")
    elif not YOUTUBE_API_KEY:
        print("오류: YOUTUBE_API_KEY가 설정되지 않았습니다. 환경 변수를 확인해주세요.")
    else:
        bot.run(DISCORD_BOT_TOKEN)
