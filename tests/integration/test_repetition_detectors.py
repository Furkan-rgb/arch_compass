"""The other half of the catalogue: repetition with no owner.

The sole-implementation detector can only ever find too much structure. On a real
repository whose actual problem was the opposite — a coding agent spreading vendor
customisations through modules that had no reason to know a vendor existed — it reported
nothing, and nothing reads as approval. These are the detectors for that direction.

Both are name-based and both say so in their limitations. They are candidates, never
verdicts: two modules can define `TIMEOUT` about unrelated things, and a composition root
naming a backend is doing its job.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.adapters.analysis import PythonAstRepositoryAnalyzer
from archcompass.boundary.atlas import FindingPattern
from archcompass.boundary.finding_detectors import detect_finding_candidates


def _atlas(root: Path, files: dict[str, str]):
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return PythonAstRepositoryAnalyzer().analyze(root)


def _of(atlas, pattern: FindingPattern):
    return [item for item in detect_finding_candidates(atlas) if item.pattern is pattern]


PORT = """
from typing import Protocol


class SpeechProvider(Protocol):
    def speak(self, text: str, voice: str) -> bytes: ...
    def close(self) -> None: ...
"""

ADAPTER = """
class QwenSpeech:
    def speak(self, text: str, voice: str) -> bytes: return b""
    def close(self) -> None: return None
"""


def test_a_constant_stated_in_several_modules_becomes_one_candidate(tmp_path: Path) -> None:
    """N-ary by construction: the finding is about the set, not about any one copy."""

    atlas = _atlas(
        tmp_path / "repo",
        {
            "alpha.py": "VOICES = ('a', 'b')\n",
            "beta.py": "VOICES = ('a', 'b')\n",
            "gamma.py": "VOICES = ('a', 'b')\n",
        },
    )

    found = _of(atlas, FindingPattern.DUPLICATED_KNOWLEDGE)

    assert len(found) == 1
    assert len(found[0].participants) == 3
    measured = {item.name: item.value for item in found[0].measurements}
    assert measured["modules_stating_it"] == 3
    assert measured["distinct_values"] == 1
    assert "same value" in found[0].summary


def test_copies_that_have_already_drifted_are_reported_as_such(tmp_path: Path) -> None:
    """Drift is the evidence that nothing holds the copies together."""

    atlas = _atlas(
        tmp_path / "repo",
        {
            "alpha.py": "VOICES = ('a', 'b')\n",
            "beta.py": "VOICES = ('a', 'b', 'c')\n",
        },
    )

    found = _of(atlas, FindingPattern.DUPLICATED_KNOWLEDGE)

    assert len(found) == 1
    measured = {item.name: item.value for item in found[0].measurements}
    assert measured["distinct_values"] == 2
    assert "do not all hold the same value" in found[0].summary


def test_a_constant_with_one_home_is_not_a_candidate(tmp_path: Path) -> None:
    """One module stating a fact is a module owning it, which is the point."""

    atlas = _atlas(
        tmp_path / "repo",
        {"alpha.py": "VOICES = ('a',)\n", "beta.py": "from alpha import VOICES\n"},
    )

    assert _of(atlas, FindingPattern.DUPLICATED_KNOWLEDGE) == []


def test_the_value_is_fingerprinted_and_never_carried(tmp_path: Path) -> None:
    """A constant is exactly the kind of thing that turns out to be a key.

    Whatever an atlas records reaches every prompt and every stored review, so the literal
    must not survive the parse — only whether two of them agree.
    """

    secret = "sk-do-not-copy-me-anywhere"
    atlas = _atlas(
        tmp_path / "repo",
        {"alpha.py": f"TOKEN = {secret!r}\n", "beta.py": f"TOKEN = {secret!r}\n"},
    )

    assert secret not in atlas.model_dump_json()
    found = _of(atlas, FindingPattern.DUPLICATED_KNOWLEDGE)
    assert len(found) == 1
    assert secret not in found[0].model_dump_json()


def test_a_vendor_named_outside_its_package_becomes_a_candidate(tmp_path: Path) -> None:
    """The finding the origin of this project was about.

    A boundary existing is not a boundary being used: the port is right there, and the web
    layer still spells the vendor's name into a string it will have to edit by hand.
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "provider/registry.py": "from .qwen import QwenSpeech\n",
            "web/__init__.py": "",
            "web/pages.py": "TITLE = 'Narrated with Qwen3-TTS'\n",
        },
    )

    found = _of(atlas, FindingPattern.SCATTERED_CONCEPT)

    assert len(found) == 1
    named = {item.qualified_name for item in found[0].participants}
    assert any(item.endswith("provider.qwen") for item in named)
    assert any(item.endswith("web.pages") for item in named)
    # Its own package names it on purpose: the registry is the wiring that must choose.
    assert not any(item.endswith("provider.registry") for item in named)


def test_a_concept_named_only_inside_its_own_package_is_not_scattered(
    tmp_path: Path,
) -> None:
    atlas = _atlas(
        tmp_path / "repo",
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "provider/registry.py": "from .qwen import QwenSpeech\n",
            "web/__init__.py": "",
            "web/pages.py": "TITLE = 'Narrated'\n",
        },
    )

    assert _of(atlas, FindingPattern.SCATTERED_CONCEPT) == []


def test_a_module_named_after_the_concept_its_port_abstracts_is_not_a_leak(
    tmp_path: Path,
) -> None:
    """`voices.py` behind `VoiceValidator` is the domain's word, not a vendor's.

    Without this the detector reported every module that said "voices" in a repository
    about voices, which is a word count rather than a finding.
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "preflight/__init__.py": "",
            "preflight/voices.py": (
                "from typing import Protocol\n\n\n"
                "class VoiceValidator(Protocol):\n"
                "    def check(self, voice: str, strict: bool) -> bool: ...\n"
                "    def close(self) -> None: ...\n\n\n"
                "class QwenVoiceValidator:\n"
                "    def check(self, voice: str, strict: bool) -> bool: return True\n"
                "    def close(self) -> None: return None\n"
            ),
            "web/__init__.py": "",
            "web/pages.py": "def render(voices: list[str]) -> str: return ''\n",
        },
    )

    assert _of(atlas, FindingPattern.SCATTERED_CONCEPT) == []


def test_a_docstring_mentioning_a_vendor_is_not_a_leak(tmp_path: Path) -> None:
    """Prose about a backend is documentation; the question is whether *code* must know."""

    atlas = _atlas(
        tmp_path / "repo",
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "web/__init__.py": "",
            "web/pages.py": '"""Rendering, currently backed by Qwen in production."""\n',
        },
    )

    assert _of(atlas, FindingPattern.SCATTERED_CONCEPT) == []


def test_every_candidate_states_what_its_method_could_not_see(tmp_path: Path) -> None:
    """A detector claiming no limitations claims the static view is complete."""

    atlas = _atlas(
        tmp_path / "repo",
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "web/__init__.py": "",
            "web/pages.py": "TITLE = 'Qwen'\nVOICES = ('a',)\n",
            "other.py": "VOICES = ('a',)\n",
        },
    )

    candidates = detect_finding_candidates(atlas)

    assert candidates
    for candidate in candidates:
        assert candidate.limitations.strip()
        for measurement in candidate.measurements:
            assert measurement.limitations.strip()
            assert measurement.definition.strip()


def test_a_leaked_name_is_located_where_it_leaks_not_at_the_top_of_the_file(
    tmp_path: Path,
) -> None:
    """The regression for evidence that did not contain the thing it was evidence of.

    A scattered concept's participants are whole modules, so the detector had no declaration
    span to give them and wrote line 1. Line 1 of a Python file is the docstring, and the
    excerpt service resolves a span to the text at it — so a reader asking to see a vendor
    name that had leaked into five modules was shown five docstrings, none of which named it.
    The advisor said it could not show the leak, and it was right.

    Every mention now carries its line, so the participant points at one that really names
    the concept, and the count says whether it is an isolated import or threaded through.
    """

    root = tmp_path / "repo"
    atlas = _atlas(
        root,
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "web/__init__.py": "",
            # The name appears twice and never on line 1, which is a docstring that does not
            # contain it — the exact shape that produced the empty evidence.
            "web/pages.py": (
                '"""The page a listener lands on."""\n'
                "\n"
                "HEADING = 'Welcome'\n"
                "\n"
                "TITLE = 'Narrated with Qwen3-TTS'\n"
                "FOOTER = 'Powered by Qwen'\n"
            ),
        },
    )

    found = _of(atlas, FindingPattern.SCATTERED_CONCEPT)
    leaked = next(
        item for item in found[0].participants if item.qualified_name.endswith("web.pages")
    )
    assert leaked.location is not None

    lines = (root / "web/pages.py").read_text(encoding="utf-8").splitlines()
    named = lines[leaked.location.start_line - 1]
    assert "Qwen" in named, f"the located line does not name the concept: {named!r}"
    # The first site, so a reader lands on the leak rather than in the middle of the file.
    assert leaked.location.start_line == 5
    # And the count is carried, because one import and a name threaded through a request
    # path are different findings that a single span cannot tell apart.
    assert "Named on 2 lines here." in leaked.role


def test_a_name_used_once_says_nothing_about_a_count(tmp_path: Path) -> None:
    """"Named on 1 lines here" would be noise, and reads as though it were measured."""

    atlas = _atlas(
        tmp_path / "repo",
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "web/__init__.py": "",
            "web/pages.py": "TITLE = 'Narrated with Qwen3-TTS'\n",
        },
    )

    found = _of(atlas, FindingPattern.SCATTERED_CONCEPT)
    leaked = next(
        item for item in found[0].participants if item.qualified_name.endswith("web.pages")
    )

    assert leaked.role == "Names 'qwen' from outside the package that owns it."
