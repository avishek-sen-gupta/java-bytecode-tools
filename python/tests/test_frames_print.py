"""Tests for frames_print with flat {nodes, calls, metadata} schema."""

SIG_MAIN = "<com.example.App: void main(String[])>"
SIG_SVC = "<com.example.Svc: void handle()>"
SIG_DAO = "<com.example.Dao: void save()>"


def _node(sig: str, cls: str, method: str, line_start: int, line_end: int) -> dict:
    return {
        "class": cls,
        "method": method,
        "methodSignature": sig,
        "lineStart": line_start,
        "lineEnd": line_end,
        "sourceLineCount": line_end - line_start + 1,
    }


NODES = {
    SIG_MAIN: _node(SIG_MAIN, "com.example.App", "main", 5, 15),
    SIG_SVC: _node(SIG_SVC, "com.example.Svc", "handle", 20, 40),
    SIG_DAO: _node(SIG_DAO, "com.example.Dao", "save", 50, 70),
}

CALLS = [
    {"from": SIG_MAIN, "to": SIG_SVC, "callSiteLine": 10},
    {"from": SIG_SVC, "to": SIG_DAO, "callSiteLine": 35},
]


class TestFindRoots:
    def test_node_with_no_incoming_is_root(self):
        from frames_print import find_roots

        roots = find_roots(set(NODES.keys()), CALLS)
        assert SIG_MAIN in roots

    def test_non_root_excluded(self):
        from frames_print import find_roots

        roots = find_roots(set(NODES.keys()), CALLS)
        assert SIG_SVC not in roots
        assert SIG_DAO not in roots


class TestCollectPaths:
    def test_single_chain_collected(self):
        from frames_print import collect_paths

        paths = collect_paths({SIG_MAIN}, SIG_DAO, CALLS)
        assert [SIG_MAIN, SIG_SVC, SIG_DAO] in paths

    def test_no_path_returns_empty(self):
        from frames_print import collect_paths

        paths = collect_paths({SIG_MAIN}, SIG_MAIN, CALLS)
        assert paths == []


class TestFormatFrame:
    def test_format_shows_class_method_lines(self):
        from frames_print import format_frame

        result = format_frame(NODES[SIG_DAO])
        assert "com.example.Dao.save" in result
        assert "L50-70" in result
        assert "21 lines" in result


class TestFormatPath:
    def test_single_frame_no_callsite(self):
        from frames_print import format_path

        result = format_path([SIG_MAIN], NODES, CALLS, 0)
        assert "Chain 1:" in result
        assert "@L" not in result

    def test_second_frame_shows_callsite(self):
        from frames_print import format_path

        result = format_path([SIG_MAIN, SIG_SVC, SIG_DAO], NODES, CALLS, 0)
        assert "@L10" in result
        assert "@L35" in result

    def test_chain_index_in_header(self):
        from frames_print import format_path

        result = format_path([SIG_MAIN], NODES, CALLS, 2)
        assert "Chain 3:" in result


class TestFormatFrames:
    def test_header_shows_target(self):
        from frames_print import format_frames

        data = {
            "nodes": NODES,
            "calls": CALLS,
            "metadata": {"tool": "frames", "toClass": "com.example.Dao", "toLine": 55},
        }
        result = format_frames(data)
        assert "com.example.Dao" in result
        assert "55" in result

    def test_shows_chain_count(self):
        from frames_print import format_frames

        data = {
            "nodes": NODES,
            "calls": CALLS,
            "metadata": {"tool": "frames", "toClass": "com.example.Dao", "toLine": 55},
        }
        result = format_frames(data)
        assert "1 chain" in result

    def test_no_paths_message(self):
        from frames_print import format_frames

        data = {
            "nodes": {},
            "calls": [],
            "metadata": {"tool": "frames", "toClass": "com.example.Dao", "toLine": 55},
        }
        result = format_frames(data)
        assert "no paths" in result

    def test_from_class_shown_when_present(self):
        from frames_print import format_frames

        data = {
            "nodes": NODES,
            "calls": CALLS,
            "metadata": {
                "tool": "frames",
                "toClass": "com.example.Dao",
                "toLine": 55,
                "fromClass": "com.example.App",
                "fromLine": 5,
            },
        }
        result = format_frames(data)
        assert "com.example.App" in result
