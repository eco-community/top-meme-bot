import aiohttp
import discord
import logging
import redis

import config

logging.basicConfig(filename="eco-memes.log", level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")


class EcoBot(discord.Client):
    # under this key we will store set() of posts that we've replied to the top meme channel
    REPLIED_POSTS_SET = "REPLIED_POSTS_SET"
    SETTINGS = "SETTINGS"
    MEME_REACTION_LIMIT = "MEME_REACTION_LIMIT"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis = redis.StrictRedis(host=config.REDIS_HOST_URL, port=6379, db=0)

        # If there are no limit in the Redis database, then we initialize them here with default value 10
        if not self.redis.hget(self.SETTINGS, self.MEME_REACTION_LIMIT):
            self.redis.hset(self.SETTINGS, self.MEME_REACTION_LIMIT, 10)

    def is_message_meme(self, message) -> bool:
        """
        If message doesn't have any embeds or attachments probably it is not a meme
        :param message: Discord Message Object
        :return: bool
        """
        if not (message.attachments or message.embeds):
            return False
        return True

    def is_cached(self, message_id: str) -> bool:
        # if not cached
        if not self.redis.sismember(self.REPLIED_POSTS_SET, message_id):
            return False
        return True

    def get_limit(self) -> int:
        """
        Get current reactions limit
        :return: limit
        """
        return int(self.redis.hget(self.SETTINGS, self.MEME_REACTION_LIMIT))

    def set_limit(self, limit: int):
        """
        Set reactions limit
        :param limit:
        :return: None
        """
        self.redis.hset(self.SETTINGS, self.MEME_REACTION_LIMIT, limit)

    async def reply_top_meme(self, message):
        """
        Function that replies message with embeds and files to Top-Meme channel
        :param message: Discord Message Object
        :return: None
        """
        user = client.get_user(message.author.id)
        files = [await pp.to_file() for pp in message.attachments]

        # create async http transport session
        async with aiohttp.ClientSession() as session:
            # get Webhook object from url and session
            webhook = discord.Webhook.from_url(config.HOOK, adapter=discord.AsyncWebhookAdapter(session))

            # bot takes username, avatar, copying all content and replying to Top-Meme channel
            await webhook.send(username=user.name, content=message.content, avatar_url=user.avatar_url, files=files)

    async def on_ready(self):
        logging.info(f"Logged in as {self.user.name}")

    async def command_resolver(self, message, channel):
        """
        A function that resolves which command to execute
        :param message: Discord Message Object
        :param channel: Discord Channel Object
        :return: None
        """
        if message.content.startswith('!meme.get_limit'):
            limit = self.get_limit()
            await channel.send(f"**Current meme limit is:** __{limit}__")
        elif message.content.startswith('!meme.set_limit'):
            # Split the message content by spaces
            limit = message.content.split(' ')
            # Get number of elements
            args_len = len(limit) - 1

            # Check if the user sent just !meme.set_limit
            if args_len == 0:
                await channel.send(f"**Specify the limit**")

            # Check if the user sent too many arguments
            elif args_len > 1:
                await channel.send(f"**Invalid command usage**\nCorrect format is `!meme.set_limit NUMBER`")
            # Correct input
            else:
                try:
                    self.set_limit(int(limit[args_len]))
                    await channel.send('**The reaction limit has been successfully updated**')
                except Exception as e:
                    await channel.send('**Something went wrong, but I will definitely figure it out!**')
                    logging.error(e)
        else:
            await channel.send(f"**Unknown command**")

    async def on_message(self, message):
        """
        Function that adds emoji for new messages which contains embed or file
        :param message: Discord Message Object
        :return: None
        """
        # Check if the user sent command
        if message.content.startswith('!'):
            channel = message.channel
            await self.command_resolver(message, channel)

        # The user sent common message
        else:
            # ignore message if author is bot or if message not in Meme-Channel
            if message.channel.id != config.MEME_CHANNEL_ID or message.author.id == self.user.id:
                return

            # ignore message if it has not attachments or embeds
            if not self.is_message_meme(message=message):
                return

            # add reaction to message
            await message.add_reaction(config.REACTION)

    async def on_raw_reaction_add(self, payload):
        """
        When certain meme gets reactions more than MIN_REACTIONS_NUMBER_TO_REPOST we will repost it to top_memes
        :param payload: Discord RawReactionActionEvent Object
        :return: None
        """
        message_id = payload.message_id

        if payload.channel_id == config.MEME_CHANNEL_ID and not self.is_cached(message_id):
            unique_users = set()
            message = await self.get_channel(payload.channel_id).fetch_message(message_id)

            # ensure that message is meme
            if not self.is_message_meme(message=message):
                return

            # count unique users for message
            for reaction in message.reactions:
                async for user in reaction.users():
                    if user.id == self.user.id:
                        continue
                    unique_users.add(user)

            # check if meme got enought unique users
            if len(unique_users) >= config.MIN_REACTIONS_NUMBER_TO_REPOST:
                # save to cache
                self.redis.sadd(self.REPLIED_POSTS_SET, message_id)
                await self.reply_top_meme(message)
            logging.info(f"{payload.emoji} {len(unique_users)}")


if __name__ == "__main__":
    # This bot requires the members and reactions intents.
    intents = discord.Intents.default()
    intents.members = True

    client = EcoBot(intents=intents)
    client.run(config.TOKEN)
