import aiohttp
import discord
import logging

import config

logging.basicConfig(filename="eco-memes.log", level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")


class EcoBot(discord.Client):
    def is_message_meme(self, message) -> bool:
        """
        If message doesn't have any embeds or attachments probably it is not a meme
        :param message: Discord Message Object
        :return: bool
        """
        if not (message.attachments or message.embeds):
            return False
        return True

    async def reply_top_meme(self, message):
        """
        Function that replies message with embeds and files to Top-Meme channel
        :param message: Discord Message Object
        :return: void
        """
        user = client.get_user(message.author.id)
        files = [await pp.to_file() for pp in message.attachments]

        # create async http transport session
        async with aiohttp.ClientSession() as session:
            # get Webhook object from url and session
            webhook = discord.Webhook.from_url(config.HOOK, adapter=discord.AsyncWebhookAdapter(session))

            # bot takes username, avatar, copying all content and replying to Top-Meme channel
            await webhook.send(username=user.name, content=message.content,
                               avatar_url=user.avatar_url, files=files)

    async def on_ready(self):
        logging.info(f"Logged in as {self.user.name}")

    async def on_message(self, message):
        """
        Function that adds emoji for new messages which contains embed or file
        :param message: Discord Message Object
        :return: void
        """
        # ignore message if author is bot or if message not in Meme-Channel
        if message.channel.id != config.MEME_CHANNEL_ID or message.author.id == self.user.id:
            return

        # ignore message if it has not attachments or embeds
        if not (message.attachments or message.embeds):
            return

        # add reaction to message
        await message.add_reaction(config.REACTION)

    async def on_raw_reaction_add(self, payload):
        """
        When certain meme gets reactions more than MIN_REACTIONS_NUMBER_TO_REPOST we will repost it to top_memes
        :param payload: Discord RawReactionActionEvent Object
        :return: void
        """
        if payload.channel_id == config.MEME_CHANNEL_ID:
            unique_users = set()
            message = await self.get_channel(payload.channel_id).fetch_message(payload.message_id)

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
                await self.reply_top_meme(message)
            logging.info(f"{payload.emoji} {len(unique_users)}")


# This bot requires the members and reactions intents.
intents = discord.Intents.default()
intents.members = True

client = EcoBot(intents=intents)
client.run(config.TOKEN)
