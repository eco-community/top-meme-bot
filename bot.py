import discord
import logging

import config

logging.basicConfig(filename="eco-memes.log", level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")


class EcoBot(discord.Client):
    def is_message_meme(self, message) -> bool:
        """If message doesn't have any embeds or attachments probably it is not a meme"""
        if not (message.attachments or message.embeds):
            return False
        return True

    async def on_ready(self):
        print('Logged in as ' + self.user.name)
        # TODO run job here

    async def on_message(message):
        if message.channel.id != MEME_CHANNEL_ID:
            return
        if message.author.id == bot.user.id:
            return
        if not (message.attachments or message.embeds):
            return
        await message.add_reaction(REACTION)

    async def on_raw_reaction_add(self, payload):
        """When certain meme gets reactions more than MIN_REACTIONS_NUMBER_TO_REPOST we will repost it to top_memes"""

        if payload.channel_id == config.MEME_CHANNEL_ID:
            unique_users = set()
            message = await self.get_channel(payload.channel_id).fetch_message(payload.message_id)

            # ensure that message is meme
            if not self.is_message_meme(message=message):
                return

            # count unique users for message
            for reaction in message.reactions:
                async for user in reaction.users():
                    unique_users.add(user)

            # check if meme got enought unique users
            if len(unique_users) >= config.MIN_REACTIONS_NUMBER_TO_REPOST:
                print("reposting meme...")
            logging.info(f"{payload.emoji} {len(unique_users)}")


# This bot requires the members and reactions intents.
intents = discord.Intents.default()
intents.members = True

client = EcoBot(intents=intents)
client.run(config.TOKEN)
