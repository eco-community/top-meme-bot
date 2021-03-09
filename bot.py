import aiohttp
import discord
import logging
import redis
from discord.ext import commands

import config

# initialize bot params
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='!reactions.', intents=intents)

# initialize redis
redis = redis.StrictRedis(host=config.REDIS_HOST_URL, port=6379, db=0)

# setup logger
logging.basicConfig(filename="eco-memes.log", level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")


def get_reactions_count() -> int:
    """
    Get current reactions count
    :return: count
    """
    return int(redis.hget(config.SETTINGS, config.MEME_REACTION_COUNT))


def set_reactions_count(count: int):
    """
    Set reactions count
    :param count:
    :return: None
    """
    redis.hset(config.SETTINGS, config.MEME_REACTION_COUNT, count)


def is_cached(message_id: str) -> bool:
    """
    Check if message_id is cached
    :param message_id: Discord Message ID
    :return: bool
    """
    # if not cached
    if not redis.sismember(config.REPLIED_POSTS_SET, message_id):
        return False
    return True


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
        await webhook.send(username=user.name, content=message.content, avatar_url=user.avatar_url, files=files)


@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user.name}")
    # If there are no reactions count in the Redis database, then we initialize it here with default value 10
    if not redis.hget(config.SETTINGS, config.MEME_REACTION_COUNT):
        set_reactions_count(10)


@commands.has_any_role('Eco Team')
@bot.command('get_count')
async def get_count(ctx):
    """
    Command that replies reactions count
    :param ctx: Discord Context object
    :return: None
    """
    count = get_reactions_count()
    await ctx.send(f"**Current meme count is:** __{count}__")


@commands.has_any_role('Eco Team')
@bot.command('set_count')
async def set_count(ctx, *args):
    """
    Command that sets reactions count
    :param ctx: Discord Context object
    :param args: Tuple of arguments
    :return: None
    """
    # Get number of elements
    args_len = len(args)

    # Check if the user sent just !reactions.set_count
    if args_len == 0:
        await ctx.send(f"**Specify the count**")

    # Check if the user sent too many arguments
    elif args_len > 1:
        await ctx.send(f"**Invalid command usage**\nCorrect format is `!reactions.set_count NUMBER`")
    # Correct input
    else:
        try:
            set_reactions_count(int(args[0]))
            await ctx.send(f"**The reaction count has been updated to {args[0]}**")
        except Exception as e:
            await ctx.send('**Something went wrong, but I will definitely figure it out!**')
            logging.error(e)


@commands.has_any_role('Eco Team')
@bot.listen('on_message')
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
    message_id = payload.message_id

    if payload.channel_id == config.MEME_CHANNEL_ID and not is_cached(message_id):
        unique_users = set()
        message = await bot.get_channel(payload.channel_id).fetch_message(message_id)

        # ensure that message is meme
        if not is_message_meme(message=message):
            return

        # count unique users for message
        for reaction in message.reactions:
            async for user in reaction.users():
                if user.id == bot.user.id:
                    continue
                unique_users.add(user)

        # check if meme got enought unique users
        if len(unique_users) >= get_reactions_count():
            # save to cache
            redis.sadd(config.REPLIED_POSTS_SET, message_id)
            await reply_top_meme(message)
        logging.info(f"{payload.emoji} {len(unique_users)}")


bot.run(config.TOKEN)
