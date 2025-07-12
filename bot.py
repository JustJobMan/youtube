import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import googleapiclient.discovery
from datetime import datetime, timedelta
import re
import pytz

if os.path.exists('config.env'):
    load_dotenv('config.env')

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

@bot.event
async def on_ready():
    print(f'봇이 로그인되었습니다: {bot.user.name} (ID: {bot.user.id})')
    print('------')

@bot.command(name='링크')
async def youtube_link(ctx, url: str):
    """
    유튜브 라이브 링크를 입력하면 방송 시작/종료 시간 및 총 방송 시간을 알려줍니다.
    사용법: !링크 [유튜브 라이브 링크주소]
    """
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
            maxResults=5
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
                f"   - 설명: {channel_description[:100]}...\n"
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

# !트렌드 명령어 처리: 유튜브 인기/관련 동영상 검색 (horror movie로 변경)
@bot.command(name='트렌드')
async def youtube_ghost_haunted_trend(ctx):
    """
    유튜브에서 'horror movie' 관련 인기 동영상을 검색하고 조회수를 표시합니다.
    사용법: !트렌드
    """
    await ctx.send("유튜브에서 'horror movie' 관련 인기 동영상을 검색 중입니다. 잠시만 기다려 주세요...")

    try:
        search_request = youtube.search().list(
            part="snippet",
            q="horror movie", # 'horror movie'로 변경
            type="video",
            order="viewCount",
            maxResults=5
        )
        search_response = search_request.execute()

        videos = search_response.get('items', [])
        if not videos:
            await ctx.send("'horror movie' 관련 인기 동영상을 찾을 수 없습니다.")
            return

        video_ids = [video['id']['videoId'] for video in videos]

        videos_info_request = youtube.videos().list(
            part="statistics",
            id=",".join(video_ids)
        )
        videos_info_response = videos_info_request.execute()

        view_counts = {}
        for item in videos_info_response.get('items', []):
            video_id = item['id']
            view_count = item['statistics'].get('viewCount', '0')
            view_counts[video_id] = int(view_count)

        response_message = "'horror movie' 관련 인기 동영상:\n"
        for i, video in enumerate(videos):
            video_id = video['id']['videoId']
            video_title = video['snippet']['title']
            channel_title = video['snippet']['channelTitle']
            
            current_view_count = view_counts.get(video_id, 0)
            formatted_view_count = f"{current_view_count:,}"

            response_message += (
                f"\n**{i+1}. {video_title}**\n"
                f"   - 채널: {channel_title}\n"
                f"   - 조회수: {formatted_view_count}\n"
                f"   - 링크: https://www.youtube.com/watch?v={video_id}\n"
            )

        await ctx.send(response_message)

    except googleapiclient.errors.HttpError as e:
        if e.resp.status == 403:
            await ctx.send("유튜브 API 할당량 초과 또는 API 키에 문제가 있습니다. 잠시 후 다시 시도하거나 API 키를 확인해주세요.")
        elif e.resp.status == 400:
            await ctx.send("유튜브 API 요청이 잘못되었습니다. 검색어에 문제가 있을 수 있습니다.")
        else:
            await ctx.send(f"유튜브 API 호출 중 오류가 발생했습니다: {e}")
        print(f"YouTube API Error: {e}")
    except Exception as e:
        await ctx.send(f"오류가 발생했습니다: {e}")
        print(f"Error: {e}")

if __name__ == '__main__':
    if not DISCORD_BOT_TOKEN:
        print("오류: DISCORD_BOT_TOKEN이 설정되지 않았습니다. 환경 변수를 확인해주세요.")
    elif not YOUTUBE_API_KEY:
        print("오류: YOUTUBE_API_KEY가 설정되지 않았습니다. 환경 변수를 확인해주세요.")
    else:
        bot.run(DISCORD_BOT_TOKEN)
