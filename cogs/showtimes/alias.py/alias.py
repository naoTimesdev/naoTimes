import asyncio
import logging
from typing import List, Optional

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.showtimes.models import ShowtimesProject
from naotimes.views.multi_view import Selection


class ShowtimesAlias(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.Alias")

    @commands.group(name="alias")
    @commands.guild_only()
    async def _showalias_main(self, ctx: naoTimesContext):
        if not ctx.invoked_subcommand:
            if not ctx.empty_subcommand(2):
                return
            server_id = ctx.guild.id
            self.logger.info(f"Requested !alias content for {server_id}")
            srv_data = await self.bot.showqueue.fetch_database(server_id)
            if srv_data is None:
                return  # no showtimes data

            self.logger.info("Server found")
            if not srv_data.is_admin(ctx.author.id):
                self.logger.warning(f"{server_id}: not the server admin")
                return await ctx.send("Hanya admin yang dapat mengubah/menambah alias")

            if len(srv_data.projects) < 1:
                self.logger.warning(f"{server_id}: no registered data on database.")
                return await ctx.send("Tidak ada anime yang terdaftar di database")

            self.logger.info(f"{server_id}: generating initial data...")
            embed = discord.Embed(title="Alias", color=0x56ACF3)
            embed.add_field(name="Memulai proses!", value="Mempersiapkan...")
            embed.set_footer(text="Dibawakan oleh naoTimes™", icon_url="https://p.n4o.xyz/i/nao250px.png")
            base_message = await ctx.send(embed=embed)

            selected_project: Optional[ShowtimesProject] = None
            new_alias: Optional[str] = None

            async def _select_project():
                self.logger.info(f"{server_id}: processing anime...")
                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(
                    name="Judul/Garapan Anime", value="Ketik judul animenya (yang asli), bisa disingkat"
                )
                embed.set_footer(text="Dibawakan oleh naoTimes™", icon_url="https://p.n4o.xyz/i/nao250px.png")
                await base_message.edit(embed=embed)

                await_this = await ctx.wait_content("Ketik judulnya...", timeout=None)
                if not await_this:
                    self.logger.info(f"{server_id}: user cancelled")
                    return False

                find_match = await self.bot.loop.run_in_executor(
                    None, srv_data.find_projects, await_this, True
                )
                if len(find_match) < 1:
                    self.logger.info(f"{server_id}: no match found")
                    await ctx.send("Tidak dapat menemukan judul tersebut di database")
                    return False
                if len(find_match) > 1:
                    self.logger.info(f"{server_id}: multiple match found")
                    selected_project = await ctx.select_single(
                        find_match,
                        lambda x: Selection(x.title, x.id),
                        content="Pilih judul yang anda maksud!",
                    )
                    if selected_project is None:
                        await ctx.send("**Dibatalkan!**")
                        return False
                    find_match = [selected_project]

                selected_project = find_match[0]

                self.logger.info(f"{server_id}: selected project {selected_project.title}")
                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(name="Apakah benar?", value=f"Judul: **{selected_project.title}**")
                embed.set_footer(text="Dibawakan oleh naoTimes™", icon_url="https://p.n4o.xyz/i/nao250px.png")
                await base_message.edit(embed=embed)

                is_confirm = await ctx.confirm("Pastikan anime yang dipilih sudah benar, lanjutkan?")
                if not is_confirm:
                    await ctx.send("**Dibatalkan!**")
                    return False
                self.logger.info(f"{server_id}: confirmed")
                return selected_project

            async def _select_alias():
                self.logger.info(f"{server_id}: processing alias...")
                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(
                    name="Alias",
                    value="Ketik alias yang diinginkan",
                    inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™",
                    icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await base_message.edit(embed=embed)

                await_this = await ctx.wait_content("Ketik aliasnya...", True, True, None, allow_cancel=False)
                if not isinstance(await_this, str):
                    self.logger.info(f"{server_id}: user cancelled")
                    return False

                self.logger.info(f"{server_id}: alias added")
                return await_this

            selected_project = await _select_project()
            if not selected_project:
                return

            result = await _select_alias()
            if not result:
                return await ctx.send("**Dibatalkan!**")
            new_alias = result

            first_time = True
            skip_reload = False
            while True:
                embed = discord.Embed(
                    title="Alias",
                    description="Periksa data!\nReact jika ingin diubah.",
                    color=0xE7E363,
                )
                embed.add_field(
                    name="1⃣ Anime/Garapan",
                    value=selected_project.title,
                    inline=False,
                )
                embed.add_field(
                    name="2⃣ Alias",
                    value=new_alias,
                    inline=False,
                )
                embed.add_field(
                    name="Lain-Lain",
                    value="✅ Tambahkan!\n❌ Batalkan!",
                    inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™",
                    icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                if first_time:
                    await base_message.delete()
                    base_message = await ctx.send(embed=embed)
                    first_time = False
                else:
                    await base_message.edit(embed=embed)

                to_react = ["1⃣", "2⃣", "✅", "❌"]
                if not skip_reload:
                    for reaction in to_react:
                        await base_message.add_reaction(reaction)
                else:
                    skip_reload = False

                def check_reaction(reaction: discord.Reaction, user: discord.Member):
                    return (
                        user.id == ctx.author.id
                        and str(reaction.emoji) in to_react
                        and reaction.message.id == base_message.id
                    )

                res: discord.Reaction
                user: discord.Member
                res, user = await self.bot.wait_for("reaction_add", check=check_reaction)
                if user != ctx.author:
                    skip_reload = True
                    continue
                await base_message.clear_reactions()
                if str(res.emoji) == "✅":
                    self.logger.info(f"{server_id}: confirmed")
                    break
                elif str(res.emoji) == "❌":
                    self.logger.info(f"{server_id}: cancelled")
                    return await ctx.send("**Dibatalkan!**")
                elif str(res.emoji) == "1⃣":
                    self.logger.info(f"{server_id}: editing title")
                    new_project = await _select_project()
                    if new_project is not None:
                        selected_project = new_project
                        new_alias = None
                    if new_alias is None:
                        new_alias = await _select_alias()
                        if not new_alias:
                            return await ctx.send("**Dibatalkan**")
                elif str(res.emoji) == "2⃣":
                    self.logger.info(f"{server_id}: editing alias")
                    temp_alias = await _select_alias()
                    if temp_alias:
                        new_alias = temp_alias

            self.logger.info(f"{server_id}: adding new alias...")
            selected_project.add_alias(new_alias)

            self.logger.info(f"{server_id}: saving...")
            srv_data.update_project(selected_project)
            await self.bot.showqueue.add_job(srv_data)
            await base_message.delete()

            self.logger.info(f"{server_id}: saving to main database...")
            success, msg = await self.bot.ntdb.update_server(srv_data)
            if not success:
                self.logger.error(f"{server_id}: failed to save to main database: {msg}")
                if srv_data.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(srv_data.id)
            await ctx.send(f"Berhasil menambah alias `{new_alias}` untuk proyek `{selected_project.title}`")

    @_showalias_main.command(name="list")
    async def _showalias_list(self, ctx: naoTimesContext, *, judul: str = None):
        server_id = ctx.guild.id
        self.logger.info(f"Requested !alias list at {server_id}")
        srv_data = await self.bot.showqueue.fetch_database(server_id)
        if srv_data is None:
            self.logger.warning(f"{server_id}: no showtimes data found")
            return

        if not judul:
            return await self.bot.showcogs.send_all_projects(ctx, srv_data)

        self.logger.info(f"{server_id}: searching for project...")
        all_matches = await self.bot.loop.run_in_executor(None, srv_data.find_projects, judul)
        if len(all_matches) < 1:
            self.logger.warning(f"{server_id}: no matches found")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.warning(f"{server_id}: multiple matches found")
            selected_anime = await ctx.select_single(
                all_matches, lambda x: Selection(x.title, x.id), content="Pilih judul yang anda maksud!"
            )
            if selected_anime is None:
                return await ctx.send("**Dibatalkan**")
            all_matches = [selected_anime]

        matched_anime = all_matches[0]
        self.logger.info(f"{server_id}: matched {matched_anime.title}")

        all_aliases = matched_anime.aliases
        real_value = ""
        if not all_aliases:
            real_value = "Tidak ada"
        else:
            numbered_aliases = []
            for i, alias in enumerate(all_aliases, 1):
                numbered_aliases.append(f"**{i}**. {alias}")
            real_value = "\n".join(numbered_aliases)

        self.logger.info(f"{server_id}: sending aliases...")
        embed = discord.Embed(title="List Alias", color=0x47E0A7)
        embed.add_field(name=matched_anime.title, value=real_value, inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

    @_showalias_main.command(name="hapus", aliases=["remove"])
    async def _showalias_hapus(self, ctx: naoTimesContext, *, judul: str = None):
        server_id = ctx.guild.id
        self.logger.info(f"Requested !alias hapus at {server_id}")
        srv_data = await self.bot.showqueue.fetch_database(server_id)
        if srv_data is None:
            self.logger.warning(f"{server_id}: no showtimes data found")
            return

        if not judul:
            return await self.bot.showcogs.send_all_projects(ctx, srv_data)

        self.logger.info(f"{server_id}: searching for project...")
        all_matches = await self.bot.loop.run_in_executor(None, srv_data.find_projects, judul, True)
        if len(all_matches) < 1:
            self.logger.warning(f"{server_id}: no matches found")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.warning(f"{server_id}: multiple matches found")
            selected_anime = await ctx.select_single(
                all_matches, lambda x: Selection(x.title, x.id), content="Pilih judul yang anda maksud!"
            )
            if selected_anime is None:
                return await ctx.send("**Dibatalkan**")
            all_matches = [selected_anime]

        matched_anime = all_matches[0]
        self.logger.info(f"{server_id}: matched {matched_anime.title}")

        all_aliases = matched_anime.aliases
        if not all_aliases:
            self.logger.warning(f"{matched_anime.title}: no aliases found")
            return await ctx.send(f"Tidak ada alias untuk judul **{matched_anime.title}**")

        alias_chunked = [all_aliases[i : i + 5] for i in range(0, len(all_aliases), 5)]

        def _create_naming_scheme(chunks: List[str]):
            numbered_chunks = []
            for i, chunk in enumerate(chunks, 1):
                numbered_chunks.append(f"**{i}**. {chunk}")
            return "\n".join(numbered_chunks)

        first_run = True
        current_page = 1
        max_page = len(alias_chunked)
        base_message: discord.Message
        self.logger.info(f"{server_id}: sending results...")
        while True:
            chunk = alias_chunked[current_page - 1]
            embed = discord.Embed(title="List Alias", color=0x47E0A7)
            embed.add_field(name=matched_anime.title, value=_create_naming_scheme(chunk), inline=False)
            embed.add_field(
                name="*Informasi*",
                value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya" "\n⏩ Selanjutnya\n❌ Batalkan",
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_run:
                base_message = await ctx.send(embed=embed)
                first_run = False
            else:
                await base_message.edit(embed=embed)

            extended_react = []
            base_emotes = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣"]  # 5 per page
            if max_page == 1 and current_page == 1:
                pass
            elif current_page == 1:
                extended_react.append("⏩")
            elif current_page == max_page:
                extended_react.append("⏪")
            elif current_page > 1 and current_page < max_page:
                extended_react.extend(["⏪", "⏩"])

            extended_react.append("❌")
            base_emotes = base_emotes[0 : len(chunk)]
            base_emotes.extend(extended_react)

            for react in base_emotes:
                await base_message.add_reaction(react)

            def check_reaction(reaction: discord.Reaction, user: discord.Member):
                if user.id != ctx.author.id:
                    return False
                if reaction.message.id != base_message.id:
                    return False
                if str(reaction.emoji) not in base_emotes:
                    return False
                return True

            res: discord.Reaction
            # user: discord.Member
            try:
                res, _ = await self.bot.wait_for("reaction_add", check=check_reaction, timeout=30.0)
            except asyncio.TimeoutError:
                return await base_message.clear_reactions()
            await base_message.clear_reactions()
            if res.emoji == "⏪":
                current_page -= 1
                if current_page < 1:
                    current_page = 1
            elif res.emoji == "⏩":
                current_page += 1
                if current_page > max_page:
                    current_page = max_page
            elif res.emoji == "❌":
                self.logger.warning(f"{server_id}: cancelling...")
                return await ctx.send("**Dibatalkan!**")
            else:
                self.logger.info(f"{server_id}: updating alias data...")
                await base_message.delete()
                index_del = base_emotes.index(str(res.emoji))
                to_be_deleted = chunk[index_del]
                self.logger.info(f"{server_id}: deleting {to_be_deleted}")
                matched_anime.remove_alias(to_be_deleted)
                srv_data.update_project(matched_anime)

                self.logger.info(f"{server_id}: saving to local cache...")
                await self.bot.showqueue.add_job(srv_data)

                await ctx.send(
                    f"Alias **{to_be_deleted}** (**`{matched_anime.title}`**) telah dihapus dari database!"
                )

                self.logger.info(f"{server_id}: updating main database...")
                success, msg = await self.bot.ntdb.update_server(srv_data)
                if not success:
                    self.logger.error(f"{server_id}: failed to update main database: {msg}")
                    if srv_data.id not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(srv_data.id)
                break


async def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    await bot.add_cog(ShowtimesAlias(bot))
