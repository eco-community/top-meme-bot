import aiohttp
import discord
import logging
import asyncio
import aioredis
from discord.ext import commands
from aioredlock import Aioredlock, LockError
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

import config
from utils import use_sentry
from constants import SENTRY_ENV_NAME, SETTINGS, MEME_REACTION_COUNT, REPLIED_POSTS_SET, ROLES_CAN_CONTROL_BOT


# initialize bot params
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="~reactions.", intents=intents)

# init sentry SDK
use_sentry(
    bot,
    dsn=config.SENTRY_API_KEY,
    environment=SENTRY_ENV_NAME,
    integrations=[AioHttpIntegration()],
)

# setup logger
logging.basicConfig(filename="eco-memes.log", level=logging.DEBUG, format="%(asctime)s %(levelname)s:%(message)s")


async def get_reactions_count() -> int:
    """
    Get current reactions count
    :return: count
    """
    reactions_count_raw = await bot.redis_client.hget(SETTINGS, MEME_REACTION_COUNT)
    return int(reactions_count_raw)


async def set_reactions_count(count: int):
    """
    Set reactions count
    :param count:
    :return: None
    """
    await bot.redis_client.hset(SETTINGS, MEME_REACTION_COUNT, count)


async def is_cached(message_id: str) -> bool:
    """
    Check if message_id is cached
    :param message_id: Discord Message ID
    :return: bool
    """
    _is_cached = await bot.redis_client.sismember(REPLIED_POSTS_SET, message_id)
    return _is_cached


def is_message_meme(message) -> bool:
    """
    If message doesn't have any embeds or attachments probably it is not a meme
    :param message: Discord Message Object
    :return: bool
    """
    if not (message.attachments or message.embeds):
        return False
    return True


async def reply_top_meme(message):
    """
    Function that replies message with embeds and files to Top-Meme channel
    :param message: Discord Message Object
    :return: None
    """
    user = bot.get_user(message.author.id)
    files = [await pp.to_file() for pp in message.attachments]

    # create async http transport session
    async with aiohttp.ClientSession() as session:
        # get Webhook object from url and session
        webhook = discord.Webhook.from_url(config.HOOK, adapter=discord.AsyncWebhookAdapter(session))
        # bot takes username, avatar, copying all content and replying to Top-Meme channel
        message_with_url = f"{message.content}\n\n[View Original](<{message.jump_url}>)"
        await webhook.send(username=user.name, content=message_with_url, avatar_url=user.avatar_url, files=files)


@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user.name}")
    # If there are no reactions count in the Redis database, then we initialize it here with default value 10
    if not await bot.redis_client.hget(SETTINGS, MEME_REACTION_COUNT):
        await set_reactions_count(10)


@commands.has_any_role(*ROLES_CAN_CONTROL_BOT)
@bot.command("get_count")
async def get_count(ctx):
    """
    Command that replies reactions count
    :param ctx: Discord Context object
    :return: None
    """
    count = await get_reactions_count()
    await ctx.send(f"**Current meme count is:** __{count}__")


@commands.has_any_role(*ROLES_CAN_CONTROL_BOT)
@bot.command("set_count")
async def set_count(ctx, set_count_to: str = "", *args):
    """
    Command that sets reactions count
    :param ctx: Discord Context object
    :param args: Tuple of arguments
    :return: None
    """

    try:
        set_to_int = int(set_count_to)
        if set_to_int <= 0:
            await ctx.send("**Invalid command usage**\nCorrect format is `!reactions.set_count INTEGER`")
            return
        await set_reactions_count(set_to_int)
        await ctx.send(f"**The reaction count has been updated to {set_to_int}**")
    except ValueError:
        await ctx.send("**Invalid command usage**\nCorrect format is `!reactions.set_count INTEGER`")


@commands.has_any_role(*ROLES_CAN_CONTROL_BOT)
@bot.listen("on_message")
async def meme_watcher(message):
    """
    Function that adds emoji for new messages which contains embed or file
    :param message: Discord Message Object
    :return: None
    """
    # ignore message if author is bot or if message not in Meme-Channel
    if message.channel.id != config.MEME_CHANNEL_ID or message.author.id == bot.user.id:
        return

    # ignore message if it has not attachments or embeds
    if not is_message_meme(message=message):
        return

    # add reaction to message
    await message.add_reaction(config.REACTION)


@bot.event
async def on_raw_reaction_add(payload):
    """
    When certain meme gets reactions more than MIN_REACTIONS_NUMBER_TO_REPOST we will repost it to top_memes
    :param payload: Discord RawReactionActionEvent Object
    :return: None
    """
    # use redis lock to prevent race condition during quick reactions on meme
    try:
        async with await bot.redis_lock.lock(f"redis_lock_for_{payload.message_id}"):
            is_meme_channel = payload.channel_id == config.MEME_CHANNEL_ID
            message_already_replied = await is_cached(payload.message_id)
            reaction_author_bot = payload.user_id == bot.user.id

            if not is_meme_channel and message_already_replied and reaction_author_bot:
                return

            message = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)

            # ensure that message is meme
            if not is_message_meme(message=message):
                return

            # count unique users for message
            unique_users = set()
            for reaction in message.reactions:
                async for user in reaction.users():
                    if user.id == bot.user.id:
                        continue
                    unique_users.add(user)

            # check if meme got enought unique users
            if len(unique_users) >= await get_reactions_count():
                # save to cache
                await bot.redis_client.sadd(REPLIED_POSTS_SET, payload.message_id)
                await reply_top_meme(message)
                # give redis sadd a little bit of breathing time
                await asyncio.sleep(0.3)
    except LockError:
        pass


if __name__ == "__main__":
    bot.redis_lock = Aioredlock(
        redis_connections=[config.REDIS_HOST_URL],
        retry_count=1,
    )
    bot.redis_client = bot.loop.run_until_complete(aioredis.create_redis_pool(address=config.REDIS_HOST_URL))
    bot.run(config.TOKEN)
