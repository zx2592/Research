#!/usr/bin/env python3
"""
Research System Telegram Bot
v3.5 (Workflow-driven research bot)

Supports workflow commands and free-form dialogue through Telegram.
"""

import asyncio
import logging
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["RUNNING_AS_BOT"] = "1"

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from research_cli import ResearchAgent


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN not found.")
    raise SystemExit(1)

print("Initializing Research Agent...")
agent = ResearchAgent()
print("Agent Ready.")

# Rate limit tracker for unauthorized attempts
_unauth_attempts: dict = {}
_UNAUTH_MAX = 5
_MAX_UNAUTH_ENTRIES = 1000


async def check_auth(update: Update) -> bool:
    chat_id = str(update.effective_chat.id)
    if chat_id != str(ALLOWED_CHAT_ID):
        # 防止内存泄漏：超过上限时清理最旧的一半条目
        if len(_unauth_attempts) >= _MAX_UNAUTH_ENTRIES:
            sorted_keys = sorted(_unauth_attempts, key=lambda k: _unauth_attempts[k])
            for k in sorted_keys[:len(sorted_keys) // 2]:
                del _unauth_attempts[k]
            logger.warning("_unauth_attempts 超过 %d 条，已清理一半", _MAX_UNAUTH_ENTRIES)
        count = _unauth_attempts.get(chat_id, 0) + 1
        _unauth_attempts[chat_id] = count
        text_preview = (update.message.text or "")[:50]
        if count <= _UNAUTH_MAX:
            logger.warning("未授权访问尝试 [%d/%d]: chat_id=%s text=%r",
                           count, _UNAUTH_MAX, chat_id, text_preview)
            await update.message.reply_text("Unauthorized.")
        # After _UNAUTH_MAX attempts, silently discard
        return False
    return True


async def send_long_message(bot, chat_id, text, parse_mode=None):
    """Send long messages safely by splitting them into chunks."""
    if not text:
        text = "Agent returned an empty response. Please try again."

    from core import settings as _settings
    max_len = _settings.bot.max_message_length

    async def safe_send(chunk, use_parse_mode=True):
        try:
            if use_parse_mode and parse_mode:
                await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=parse_mode)
            else:
                await bot.send_message(chat_id=chat_id, text=chunk)
        except Exception as exc:
            if "parse" in str(exc).lower() or "entities" in str(exc).lower():
                try:
                    await bot.send_message(chat_id=chat_id, text=chunk)
                except Exception:
                    pass
            else:
                try:
                    await bot.send_message(chat_id=chat_id, text=chunk)
                except Exception:
                    pass

    if len(text) <= max_len:
        await safe_send(text)
        return

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_pos = text.rfind("\n", 0, max_len)
        if split_pos == -1 or split_pos < max_len // 2:
            split_pos = max_len
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")

    for index, chunk in enumerate(chunks):
        await safe_send(chunk)
        if index < len(chunks) - 1:
            await asyncio.sleep(0.5)


async def run_agent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task: str,
    workflow: str | None = None,
    ticker: str | None = None,
):
    """Unified agent execution entry point for bot commands."""
    if not await check_auth(update):
        return

    label = f"[{workflow.upper()}]" if workflow else ""
    ticker_label = f" {ticker}" if ticker else ""
    status_msg = await update.message.reply_text(f"Processing {label}{ticker_label}...")

    loop = asyncio.get_running_loop()
    try:
        if workflow:
            result_text = await loop.run_in_executor(
                None, lambda: agent.run_workflow(workflow, task, ticker)
            )
        else:
            result_text = await loop.run_in_executor(None, agent.run, task)

        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=status_msg.message_id,
            )
        except Exception:
            pass

        await send_long_message(
            context.bot,
            update.effective_chat.id,
            result_text,
            parse_mode="Markdown",
        )

    except Exception as exc:
        error_text = f"Error: {exc}"
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_msg.message_id,
                text=error_text,
            )
        except Exception:
            try:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=error_text)
            except Exception:
                pass


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Research Agent v3.5\n\n"
        "Market:\n"
        "  /scan - market scan\n"
        "  /quick [Ticker] [Event] - quick event review\n"
        "  /insight - market insight\n"
        "  /theme - momentum themes\n\n"
        "Research:\n"
        "  /deep [Ticker] - deep research\n"
        "  /value [Ticker] - quality compounding analysis\n"
        "  /update [Ticker] - company update\n\n"
        "Decision:\n"
        "  /buy [Ticker] - buy review\n"
        "  /sell [Ticker] - sell review\n"
        "  /position - portfolio review\n"
        "  /rethink [Ticker] - trade rethink\n\n"
        "Knowledge:\n"
        "  /add - save latest insights\n"
        "  /verify [Claim] - fact check\n\n"
        "Push:\n"
        "  /morning - send morning brief\n"
        "  /earnings - check earnings calendar\n"
        "  /weekly - send weekly report\n\n"
        "  /reset - reset session\n\n"
        "Free-form mode: send any text directly."
    )


async def cmd_scan(update, context):
    await run_agent(
        update,
        context,
        "Run the full market scan workflow and generate the report.",
        workflow="scan",
    )


async def cmd_deep(update, context):
    args = " ".join(context.args)
    if not args:
        await update.message.reply_text("Usage: /deep [Ticker]\nExample: /deep NVDA")
        return
    ticker = args.split()[0].upper()
    await run_agent(
        update,
        context,
        f"Run deep research on {ticker} and generate the report.",
        workflow="deep",
        ticker=ticker,
    )


async def cmd_value(update, context):
    args = " ".join(context.args)
    if not args:
        await update.message.reply_text("Usage: /value [Ticker]\nExample: /value MCO")
        return
    ticker = args.split()[0].upper()
    await run_agent(
        update,
        context,
        f"Run quality compounding analysis for {ticker}.",
        workflow="value",
        ticker=ticker,
    )


async def cmd_quick(update, context):
    args = " ".join(context.args)
    if not args:
        await update.message.reply_text("Usage: /quick [Ticker] [Event]")
        return
    ticker = args.split()[0].upper()
    await run_agent(
        update,
        context,
        f"Run a quick event review for: {args}",
        workflow="quick",
        ticker=ticker,
    )


async def cmd_verify(update, context):
    args = " ".join(context.args)
    if not args:
        await update.message.reply_text("Usage: /verify [Claim]")
        return
    await run_agent(
        update,
        context,
        f"Verify the following claim: {args}",
        workflow="verify",
    )


async def cmd_add(update, context):
    await run_agent(
        update,
        context,
        "Extract the latest research insights and save them to the knowledge base.",
        workflow="add",
    )


async def cmd_update(update, context):
    args = " ".join(context.args)
    if not args:
        await update.message.reply_text("Usage: /update [Ticker]")
        return
    ticker = args.split()[0].upper()
    await run_agent(
        update,
        context,
        f"Run a company update on {ticker}.",
        workflow="update",
        ticker=ticker,
    )


async def cmd_insight(update, context):
    await run_agent(
        update,
        context,
        "Run the market insight workflow and generate the report.",
        workflow="scan",
    )


async def cmd_theme(update, context):
    await run_agent(
        update,
        context,
        "Run the momentum theme workflow.",
        workflow="theme",
    )


async def cmd_reset(update, context):
    if not await check_auth(update):
        return
    global agent
    agent = ResearchAgent()
    await update.message.reply_text("Session reset. Send a command to start again.")


async def cmd_buy(update, context):
    args = " ".join(context.args)
    if not args:
        await update.message.reply_text("Usage: /buy [Ticker]\nExample: /buy NVDA")
        return
    ticker = args.split()[0].upper()
    await run_agent(
        update,
        context,
        f"Run the buy decision workflow for {ticker}.",
        workflow="buy",
        ticker=ticker,
    )


async def cmd_sell(update, context):
    args = " ".join(context.args)
    if not args:
        await update.message.reply_text("Usage: /sell [Ticker]\nExample: /sell NVDA")
        return
    ticker = args.split()[0].upper()
    await run_agent(
        update,
        context,
        f"Run the sell decision workflow for {ticker}.",
        workflow="sell",
        ticker=ticker,
    )


async def cmd_position(update, context):
    await run_agent(
        update,
        context,
        "Run the portfolio review workflow and generate the report.",
        workflow="position",
    )


async def cmd_rethink(update, context):
    args = " ".join(context.args)
    ticker = args.split()[0].upper() if args else None
    task = f"Run a trade rethink for {ticker}." if ticker else "Run a trade rethink."
    await run_agent(update, context, task, workflow="rethink", ticker=ticker)


async def cmd_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger the morning brief push."""
    if not await check_auth(update):
        return
    await update.message.reply_text("Preparing the morning brief...")
    loop = asyncio.get_running_loop()
    try:
        import os as _os
        import sys as _sys

        _sys.path.insert(
            0,
            _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                "scripts",
            ),
        )
        from morning_scan_push import run_morning_push

        await loop.run_in_executor(None, run_morning_push)
        await update.message.reply_text("Morning brief sent.")
    except Exception as exc:
        await update.message.reply_text(f"Morning brief failed: {exc}")


async def cmd_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger the earnings calendar check."""
    if not await check_auth(update):
        return
    await update.message.reply_text("Checking the earnings calendar...")
    loop = asyncio.get_running_loop()
    try:
        import os as _os
        import sys as _sys

        _sys.path.insert(
            0,
            _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                "scripts",
            ),
        )
        from earnings_reminder import check_and_notify_earnings

        await loop.run_in_executor(None, check_and_notify_earnings)
        await update.message.reply_text("Earnings calendar check completed.")
    except Exception as exc:
        await update.message.reply_text(f"Earnings calendar check failed: {exc}")


async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger the weekly portfolio report."""
    if not await check_auth(update):
        return
    await update.message.reply_text("Generating the weekly portfolio report...")
    loop = asyncio.get_running_loop()
    try:
        import os as _os
        import sys as _sys

        _sys.path.insert(
            0,
            _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                "scripts",
            ),
        )
        from weekly_position_report import run_weekly_report

        await loop.run_in_executor(None, run_weekly_report)
        await update.message.reply_text("Weekly portfolio report sent.")
    except Exception as exc:
        await update.message.reply_text(f"Weekly portfolio report failed: {exc}")


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-form user messages."""
    if not await check_auth(update):
        return
    text = update.message.text.strip()
    if not text:
        return
    await run_agent(update, context, text)


if __name__ == "__main__":
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_start))
    application.add_handler(CommandHandler("scan", cmd_scan))
    application.add_handler(CommandHandler("deep", cmd_deep))
    application.add_handler(CommandHandler("value", cmd_value))
    application.add_handler(CommandHandler("quick", cmd_quick))
    application.add_handler(CommandHandler("verify", cmd_verify))
    application.add_handler(CommandHandler("add", cmd_add))
    application.add_handler(CommandHandler("update", cmd_update))
    application.add_handler(CommandHandler("insight", cmd_insight))
    application.add_handler(CommandHandler("theme", cmd_theme))
    application.add_handler(CommandHandler("buy", cmd_buy))
    application.add_handler(CommandHandler("sell", cmd_sell))
    application.add_handler(CommandHandler("position", cmd_position))
    application.add_handler(CommandHandler("rethink", cmd_rethink))
    application.add_handler(CommandHandler("reset", cmd_reset))
    application.add_handler(CommandHandler("morning", cmd_morning))
    application.add_handler(CommandHandler("earnings", cmd_earnings))
    application.add_handler(CommandHandler("weekly", cmd_weekly))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))

    print("Bot polling (v3.5)...")
    logging.info("Bot started polling.")
    application.run_polling()
