import logging
import re
from typing import List

import nextcord
from axew import AxewClient, BaseAxewException
from nextcord.ext import commands
from nextcord.ext.commands import Greedy

from pyro.bot import Pyro
from pyro.checks import (
    MENUDOCS_GUILD_IDS,
    PYTHON_HELP_CHANNEL_IDS,
    ensure_is_menudocs_guild,
    ensure_is_menudocs_staff,
    MenuDocsCog,
)

log = logging.getLogger(__name__)

BASE_MENUDOCS_URL = "https://github.com/menudocs"


def replied_reference(message):
    ref = message.reference
    if ref and isinstance(ref.resolved, nextcord.Message):
        return ref.resolved.to_reference()

    return None


def extract_repo(regex):
    return regex.group("repo") or "pyro"


class MenuDocs(MenuDocsCog):
    """A cog devoted to operations within the Menudocs guild"""

    def __init__(self, bot):
        self.bot: Pyro = bot
        self.logger = logging.getLogger(__name__)

        self.axew = AxewClient()

        self.issue_regex = re.compile(r"##(?P<number>[0-9]+)\s?(?P<repo>[a-zA-Z0-9]*)")
        self.pr_regex = re.compile(r"\$\$(?P<number>[0-9]+)\s?(?P<repo>[a-zA-Z0-9]*)")

        # TODO Add a way to delete embeds

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info("I'm ready!")

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message) -> None:
        if not message.guild or message.guild.id not in MENUDOCS_GUILD_IDS:
            # Not in menudocs
            return

        issue_regex = self.issue_regex.search(message.content)
        if issue_regex is not None:
            repo = extract_repo(issue_regex)
            number = issue_regex.group("number")
            url = f"{BASE_MENUDOCS_URL}/{repo}/issues/{number}"
            await message.channel.send(url)

        pr_regex = self.pr_regex.search(message.content)
        if pr_regex is not None:
            repo = extract_repo(pr_regex)
            number = pr_regex.group("number")
            url = f"{BASE_MENUDOCS_URL}/{repo}/pull/{number}"
            await message.channel.send(url)

    @commands.Cog.listener()
    async def on_thread_join(self, thread) -> None:
        if not thread.guild or thread.guild.id not in MENUDOCS_GUILD_IDS:
            # Not in menudocs
            return

        if thread.parent_id not in PYTHON_HELP_CHANNEL_IDS:
            # Not a python help channel
            return

        await thread.join()

    def extract_code(self, message: nextcord.Message) -> List[str]:
        """Extracts all codeblocks to str"""
        content: List[str] = []
        current = []
        parsed_lst: List[str] = message.content.split("\n")

        is_codeblock = False
        for item in parsed_lst:
            # Only keep items with content from codeblocks
            if "```" in item:
                is_codeblock = not is_codeblock

                if not is_codeblock:
                    content.append("\n".join(current))
                    current = []

                continue

            if is_codeblock:
                current.append(item)

        return content

    @commands.command()
    async def init(self, ctx):
        """Sends a helpful embed about how to fix import errors."""
        embed = nextcord.Embed(
            title="Seeing something like?\n`ModuleNotFoundError: No module named 'utils.utils'`\nRead on!",
            description="""
            In order to fix import issues, please add an empty file called
            `__init__.py` in your directory you are attempting to import from.
            If you are following our tutorials this is likely `utils`
            
            This happens because python is not aware of your folder
            being 'importable', by adding this file we explicitly
            declare it 'importable'. This generally resolves this issue.
            """,
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def pypi(self, ctx):
        """Sends a helpful embed about how to correctly download packages."""
        embed = nextcord.Embed(
            title="Trying to `pip install` something and getting the following?\n`Could not find a version that "
            "satisfies the requirement <package here>`",
            description="""
                Most likely the package you are trying to install isn't named
                the same as what you import. `discord.py` can be seen as an example
                here since you `import discord` and `pip install discord.py`
                
                A simple way to fix this is to google `pypi <package you want>`
                This will 9 times out of 10 provide the pypi page for said package,
                which will clearly indicate the correct way to install it.
                """,
        )
        await ctx.send(embed=embed)

    @commands.command(name="format")
    async def _format(self, ctx):
        """Sends a helpful embed about how to correctly format your question."""
        embed = nextcord.Embed(
            title="Uh oh, could you do us a favour please and re-phrase your question?",
            description="""
                > Looks like we are missing some information to properly help you out!\n
                __Please make sure you have the following:__\n
                • The code related to your question.
                • Any errors that you are receiving.
                • The taceback of your error. (If relevant)
                • The expected action/output and recieved action/output.
                """,
        )
        await ctx.send(embed=embed, reference=replied_reference(ctx.message))

    @commands.command()
    @ensure_is_menudocs_staff()
    @ensure_is_menudocs_guild()
    async def paste(
        self, ctx: commands.Context, messages: Greedy[nextcord.Message] = None
    ):
        """Given a message, create a pastebin for it"""
        if not messages:
            messages = [
                message
                async for message in ctx.channel.history(limit=2)
                if message.author != ctx.guild.me
            ]

            if len(messages) == 2 and messages[0].author.id != messages[1].author.id:
                # Make sure messages only come from the same person
                messages.pop(1)

        total_messages = len(messages)
        if total_messages > 2:
            return await ctx.send("I can only convert 1 or 2 messages to a paste")

        if total_messages == 1:
            code = self.extract_code(messages[0])
        else:
            code = self.extract_code(messages[0])
            code.extend(self.extract_code(messages[1]))

        # Ensure theres something to upload
        if not code:
            return await ctx.send("Couldn't extract anything to store")

        # Setup paste parts
        extracted_code = code[0]
        try:
            extracted_error = code[1]
        except IndexError:
            extracted_error = ""

        try:
            entry = await self.axew.async_create_paste(
                code=extracted_code,
                error=extracted_error,
                description=f"Extracted paste for {messages[0].author.display_name} in {ctx.guild.name}",
            )
        except BaseAxewException as e:
            return await ctx.send(str(e))

        mention_turnery = (
            f"{ctx.author.mention} and {messages[0].author.mention}"
            if ctx.author != messages[0].author
            else f"{ctx.author.mention}"
        )
        embed = nextcord.Embed(
            title="Find your paste here",
            url=entry.resolve_url(),
            description=f"[{entry.resolve_url()}]({entry.resolve_url()})",
            timestamp=ctx.message.created_at,
        )
        embed.set_footer(
            text="You can now delete the code and or error from your message"
        ),

        await ctx.send(f"Hey, {mention_turnery}", embed=embed)
        await ctx.message.delete()


def setup(bot):
    bot.add_cog(MenuDocs(bot))
