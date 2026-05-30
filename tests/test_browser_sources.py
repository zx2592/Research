from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.datahub.sources.bb_browser_src import BBBrowserSource
from services.datahub.sources.opencli_src import OpenCLISource


class TestOpenCLISourceCommandBuilding:
    def _make_source(self):
        with patch.object(OpenCLISource, "_check_dependency", return_value=True):
            return OpenCLISource(bin_path="opencli")

    def test_fetch_builds_current_xueqiu_command(self):
        source = self._make_source()
        with patch.object(source, "_execute_cmd", return_value=MagicMock()) as mock_exec:
            source.fetch(site="xueqiu", command="hot-stock", limit=10)

        assert mock_exec.call_args.args[0] == [
            source.bin_path,
            "xueqiu",
            "hot-stock",
            "--limit",
            "10",
            "-f",
            "json",
        ]

    def test_fetch_supports_reddit_subreddit_name_as_positional(self):
        source = self._make_source()
        with patch.object(source, "_execute_cmd", return_value=MagicMock()) as mock_exec:
            source.fetch(
                site="reddit",
                command="subreddit",
                name="WallStreetBets",
                sort="hot",
                limit=10,
            )

        assert mock_exec.call_args.args[0] == [
            source.bin_path,
            "reddit",
            "subreddit",
            "WallStreetBets",
            "--sort",
            "hot",
            "--limit",
            "10",
            "-f",
            "json",
        ]

    def test_fetch_supports_site_subcommand_style_input(self):
        source = self._make_source()
        with patch.object(source, "_execute_cmd", return_value=MagicMock()) as mock_exec:
            source.fetch(site="xueqiu/hot-stock", limit=5)

        assert mock_exec.call_args.args[0] == [
            source.bin_path,
            "xueqiu",
            "hot-stock",
            "--limit",
            "5",
            "-f",
            "json",
        ]

    def test_fetch_fans_out_multi_symbol_quotes(self):
        source = self._make_source()
        with patch.object(source, "_execute_cmd") as mock_exec:
            mock_exec.side_effect = [
                SimpleNamespace(data={"results": [{"symbol": "GOOG"}]}),
                SimpleNamespace(data={"results": [{"symbol": "SPOT"}]}),
            ]

            result = source.fetch(site="yahoo-finance", command="quote GOOG SPOT")

        assert mock_exec.call_count == 2
        assert mock_exec.call_args_list[0].args[0] == [
            source.bin_path,
            "yahoo-finance",
            "quote",
            "GOOG",
            "-f",
            "json",
        ]
        assert mock_exec.call_args_list[1].args[0] == [
            source.bin_path,
            "yahoo-finance",
            "quote",
            "SPOT",
            "-f",
            "json",
        ]
        assert result.data["results"] == [{"symbol": "GOOG"}, {"symbol": "SPOT"}]

    def test_execute_cmd_uses_replace_decode_errors(self):
        source = self._make_source()
        with patch("platform.system", return_value="Linux"), patch(
            "services.datahub.sources.opencli_src.shutil.which",
            return_value="opencli",
        ), patch("services.datahub.sources.opencli_src.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="{}", returncode=0)

            source._execute_cmd(["opencli", "xueqiu", "hot-stock", "-f", "json"], "query")

        assert mock_run.call_args.kwargs["errors"] == "replace"


class TestBBBrowserSourceExecution:
    def test_fetch_uses_replace_decode_errors(self):
        with patch.object(BBBrowserSource, "_check_dependency", return_value=True):
            source = BBBrowserSource(bin_path="bb-browser")

        with patch("services.datahub.sources.bb_browser_src.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="[]", returncode=0)
            source.fetch("xueqiu/hot-stock")

        assert mock_run.call_args.kwargs["errors"] == "replace"
