import os
import discord
from discord.ext import commands
from dotenv import load_dotenv # Render 배포 시에는 직접 사용되지 않지만, 로컬 테스트를 위해 유지합니다.
import googleapiclient.discovery
from datetime import datetime, timedelta
import re
import pytz # 시간대 변환을 위해 추가

# .env 파일에서 환경 변수 로드 (로컬 테스트용)
# Render에서는 이 부분이 필요 없습니다. 환경 변수를 직접 설정합니다.
if os.path.exists('config.env'):
    load_dotenv('config.env')

# 환경 변수에서 토큰과 API 키 불러오기 (Render에서는 여기서 직접 불러와집니다)
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

# 디스코드 인텐트 설정 (메시지 내용을 읽기 위해 필요)
intents = discord.Intents.default()
intents.message_content = True # MESSAGE CONTENT INTENT 활성화

# 봇 클라이언트 생성
bot = commands.Bot(command_prefix='!', intents=intents)

# 유튜브 API 서비스 빌드
youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# 봇이 준비되었을 때 실행되는 이벤트
@bot.event
async def on_ready():
    print(f'봇이 로그인되었습니다: {bot.user.name} (ID: {bot.user.id})')
    print('------')

# !링크 명령어 처리: 유튜브 라이브 방송 시간 계산
@bot.command(name='링크')
async def youtube_link(ctx, url: str):
    """
    유튜브 라이브 링크를 입력하면 방송 시작/종료 시간 및 총 방송 시간을 알려줍니다.
    사용법: !링크 [유튜브 라이브 링크주소]
    """
    await ctx.send("유튜브 라이브 정보를 가져오는 중입니다. 잠시만 기다려 주세요...")

    video_id = None
    # 유튜브 링크에서 video ID 추출 (다양한 링크 형식 고려)
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

        korea_tz = pytz.timezone('Asia/Seoul') # 한국 시간대 설정

        start_dt_kst = None
        end_dt_kst = None
        total_duration = None

        # 시작 시간 파싱 및 한국 시간으로 변환
        if start_time_str:
            start_dt_utc = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            start_dt_kst = start_dt_utc.astimezone(korea_tz)

        # 종료 시간 파싱 및 한국 시간으로 변환
        if end_time_str:
            end_dt_utc = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            end_dt_kst = end_dt_utc.astimezone(korea_tz)

        # 총 방송 시간 계산
        if start_dt_kst and end_dt_kst:
            total_duration = end_dt_kst - start_dt_kst
        elif start_dt_kst and not end_dt_kst: # 현재 라이브 중인 경우
            current_dt_utc = datetime.now(pytz.utc)
            current_dt_kst = current_dt_utc.astimezone(korea_tz)
            total_duration = current_dt_kst - start_dt_kst
            
        # 결과 메시지 생성
        response_message = f"**{title}** (채널: {channel_title})\n"
        response_message += "```\n" # 코드 블록 시작
        
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

        response_message += "\n" # 빈 줄 추가

        if total_duration:
            total_seconds = int(total_duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60 # 초 단위 계산 추가
            
            response_message += f"총 방송 시간 {hours}시간 {minutes}분 {seconds}초\n"
        else:
            response_message += "총 방송 시간: 계산 불가 (라이브 중이거나 정보 부족)\n"
        
        response_message += "```" # 코드 블록 끝

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


# !채널 명령어 처리: 유튜브 채널 검색
@bot.command(name='채널')
async def youtube_channel_search(ctx, *, query: str):
    """
    유튜브 채널을 검색합니다.
    사용법: !채널 [검색어]
    """
    await ctx.send(f"'{query}'에 대한 유튜브 채널을 검색 중입니다. 잠시만 기다려 주세요...")

    try:
        request = youtube.search().list(
            part="snippet",
            type="channel",
            q=query,
            maxResults=5 # 최대 5개 결과 반환
        )
        response = request.execute()

        channels = response.get('items', [])
        if not channels:
            await ctx.send(f"'{query}'에 해당하는 채널을 찾을 수 없습니다.")
            return

        response_message = f"'{query}'에 대한 검색 결과:\n"
        for i, channel in enumerate(channels):
            channel_id = channel['id']['channelId']
            channel_title = channel['snippet']['title']
            channel_description = channel['snippet']['description']
            response_message += (
                f"\n**{i+1}. {channel_title}**\n"
                f"   - ID: `{channel_id}`\n"
                f"   - 설명: {channel_description[:100]}...\n" # 설명이 길면 잘라냄
                f"   - 링크: https://www.youtube.com/channel/{channel_id}\n"
            )
        
        await ctx.send(response_message)

    except googleapiclient.errors.HttpError as e:
        if e.resp.status == 403:
            await ctx.send("유튜브 API 할당량 초과 또는 API 키에 문제가 있습니다. 잠시 후 다시 시도하거나 API 키를 확인해주세요.")
        elif e.resp.status == 400:
            await ctx.send("유튜브 API 요청이 잘못되었습니다. 검색어가 유효한지 확인해주세요.")
        else:
            await ctx.send(f"유튜브 API 호출 중 오류가 발생했습니다: {e}")
        print(f"YouTube API Error: {e}")
    except Exception as e:
        await ctx.send(f"오류가 발생했습니다: {e}")
        print(f"Error: {e}")

# 봇 실행
if __name__ == '__main__':
    if not DISCORD_BOT_TOKEN:
        print("오류: DISCORD_BOT_TOKEN이 설정되지 않았습니다. 환경 변수를 확인해주세요.")
    elif not YOUTUBE_API_KEY:
        print("오류: YOUTUBE_API_KEY가 설정되지 않았습니다. 환경 변수를 확인해주세요.")
    else:
        bot.run(DISCORD_BOT_TOKEN)