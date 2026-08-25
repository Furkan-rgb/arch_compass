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

from archcompass.analysis.adapters import PythonAstRepositoryAnalyzer
from archcompass.analysis.atlas import FindingPattern
from archcompass.analysis.detectors import detect_finding_candidates


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


def test_a_module_that_never_says_its_own_name_is_not_a_concept_that_leaked(
    tmp_path: Path,
) -> None:
    """`delta.py` declaring only `RevisionCalculator` is a file named for its job.

    The regression for the shape that made this detector's worst finding. A vendor arrives
    attached to something — `qwen.py` declares `QwenSpeech` — so a use of the name
    elsewhere is a use of *that*. A module named for what it computes declares nothing
    carrying its name, and the only place the word appears is the filename; every domain
    type that happens to contain the word then matched it, and the count read as a leak.

    Here `RevisionCalculator` never says "delta", while the repository is full of the word
    for unrelated reasons. Nothing has escaped, because nothing was ever named.
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "analysis/__init__.py": "",
            "analysis/ports.py": (
                "from typing import Protocol\n\n\n"
                "class Recalculator(Protocol):\n"
                "    def compute(self, before: int, after: int) -> int: ...\n"
            ),
            "analysis/delta.py": (
                "class RevisionCalculator:\n"
                "    def compute(self, before: int, after: int) -> int: return after\n"
            ),
            "web/__init__.py": "",
            "web/pages.py": "def render(delta: int) -> str: return str(delta)\n",
        },
    )

    assert _of(atlas, FindingPattern.SCATTERED_CONCEPT) == []


def test_a_module_named_after_its_port_is_not_a_leak_when_the_endings_differ(
    tmp_path: Path,
) -> None:
    """`retrieval.py` behind `PolicyRetriever` is the same word, spelled for its part of
    speech.

    The stem test used to ask whether one word contained the other, which is true of
    `voice`/`voices` and false of `retrieval`/`retriever` — so a module named after exactly
    the thing its port abstracts was reported, which is the finding this guard exists to
    suppress. Two suffixes on one stem is the ordinary way a port and its subject are named.
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "policies/__init__.py": "",
            "policies/ports.py": (
                "from typing import Protocol\n\n\n"
                "class PolicyRetriever(Protocol):\n"
                "    def find(self, query: str, limit: int) -> list[str]: ...\n"
            ),
            "policies/retrieval.py": (
                "class DenseRetrieval:\n"
                "    def find(self, query: str, limit: int) -> list[str]: return []\n"
            ),
            "web/__init__.py": "",
            "web/pages.py": "def render(retrieval: str) -> str: return retrieval\n",
        },
    )

    assert _of(atlas, FindingPattern.SCATTERED_CONCEPT) == []


def test_a_name_imported_across_several_lines_is_located_on_its_own_line(
    tmp_path: Path,
) -> None:
    """The parenthesised import is the common one, and it was the one located wrongly.

    An `ast.alias` was attributed to its statement, which is right for `from x import y`
    and wrong for the wrapped form: the name sits several lines below `from x import (`,
    and that opening line does not contain it. Evidence of a leak that does not contain the
    leaked name is the defect `NamedMention` was added to end, reappearing one shape along.
    """

    root = tmp_path / "repo"
    atlas = _atlas(
        root,
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "web/__init__.py": "",
            "web/pages.py": (
                "from provider.speech import (\n"
                "    SpeechProvider,\n"
                "    QwenSpeech,\n"
                ")\n"
            ),
        },
    )

    found = _of(atlas, FindingPattern.SCATTERED_CONCEPT)
    leaked = next(
        item for item in found[0].participants if item.qualified_name.endswith("web.pages")
    )
    assert leaked.location is not None

    lines = (root / "web/pages.py").read_text(encoding="utf-8").splitlines()
    assert "Qwen" in lines[leaked.location.start_line - 1]
    assert leaked.location.start_line == 3


def test_a_name_inside_a_long_literal_is_located_on_the_line_that_holds_it(
    tmp_path: Path,
) -> None:
    """A prompt or a template opens with the assignment and closes far below it.

    The literal's recorded line is where it opens, so a vendor named forty lines into a
    prompt was reported at a line reading `PROMPT = ` and an opening quote. Which names the
    literal contributes is unchanged — this is only about which of its lines each one is
    said to be on.
    """

    root = tmp_path / "repo"
    atlas = _atlas(
        root,
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "web/__init__.py": "",
            "web/pages.py": (
                "BANNER = '''\n"
                "Welcome to the library.\n"
                "Every book here is narrated with Qwen3-TTS.\n"
                "Pick a voice to begin.\n"
                "'''\n"
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
    assert leaked.location.start_line == 3


def test_a_module_whose_name_is_the_kind_of_thing_it_holds_is_not_a_leak(
    tmp_path: Path,
) -> None:
    """`nodes.py` full of `*_node` functions carries its own name and owns nothing.

    The second half of the same regression, and the one the first half missed. Requiring
    the module to declare its own name was not enough: a file of `load_context_node` and
    `select_rejudgements_node` does declare it — as the part of the name that says nothing.
    So the word has to be read where it sits. A proper noun modifies (`QwenSpeech` is a
    speech that is Qwen's); a category noun is what gets modified, and a repository is then
    full of it for reasons that have nothing to do with this module.

    Here `steps.py` holds `load_step` and `verify_step`, and a wholly unrelated `AtlasStep`
    elsewhere matched every one of them.
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "pipeline/__init__.py": "",
            "pipeline/ports.py": (
                "from typing import Protocol\n\n\n"
                "class Stage(Protocol):\n"
                "    def run(self, payload: str, attempt: int) -> str: ...\n"
            ),
            "pipeline/steps.py": (
                "class LoadStage:\n"
                "    def run(self, payload: str, attempt: int) -> str: return payload\n\n\n"
                "def load_step(payload: str) -> str: return payload\n\n\n"
                "def verify_step(payload: str) -> str: return payload\n"
            ),
            "atlas/__init__.py": "",
            "atlas/model.py": (
                "class AtlasSteps:\n"
                "    def walk(self, steps: int) -> int: return steps\n"
            ),
        },
    )

    assert _of(atlas, FindingPattern.SCATTERED_CONCEPT) == []


def test_naming_a_concept_and_reaching_it_are_counted_apart(tmp_path: Path) -> None:
    """The wiring that imports a backend and the page that spells its name are not the same.

    Both were "a module naming it from outside", and one count held them. That count is the
    only thing this pattern measures, so a judge reading it had to guess which kind of
    module the number was made of — and a guess about that is the whole verdict: importing
    an adapter is using a dependency, and writing its name into a string is the leak.

    So the graph is carried beside the name. `app.wiring` imports the adapter and appears
    in the relationships; `web.pages` only says the word, and is the difference between the
    two counts.
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "app/__init__.py": "",
            "app/wiring.py": (
                "from provider.qwen import QwenSpeech\n\n\n"
                "def build() -> QwenSpeech: return QwenSpeech()\n"
            ),
            "web/__init__.py": "",
            "web/pages.py": "TITLE = 'Narrated with Qwen3-TTS'\n",
        },
    )

    found = _of(atlas, FindingPattern.SCATTERED_CONCEPT)
    assert len(found) == 1
    measured = {item.name: item.value for item in found[0].measurements}
    assert measured["modules_naming_it_from_outside"] == 2
    assert measured["of_those_that_reach_it"] == 1

    # And the one that reaches it is named, so the judge reads placement rather than
    # reconstructing it from a number.
    reaching = {edge.source_id for edge in found[0].relationships}
    assert reaching, "a module that imports the owner left no relationship behind"


def test_a_constant_stated_only_by_tests_is_each_test_owning_its_own_setup(
    tmp_path: Path,
) -> None:
    """Five tests fixing their own fixture path is not knowledge with no owner.

    The sole-implementation detector already leaves tests out of its count and says so;
    this one counted them, so a repository's own test suite arrived as its largest source
    of duplicated knowledge. Giving those copies one owner would couple the tests to each
    other, which is the opposite of what the finding would be asking for.

    A copy shared with something that is not a test still counts, because a test holding a
    value production owns is exactly the drift this pattern exists to catch.
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "tests/__init__.py": "",
            "tests/test_alpha.py": "FIXTURE = 'cases/one'\n\n\ndef test_alpha() -> None: ...\n",
            "tests/test_beta.py": "FIXTURE = 'cases/one'\n\n\ndef test_beta() -> None: ...\n",
        },
    )

    assert _of(atlas, FindingPattern.DUPLICATED_KNOWLEDGE) == []

    shared = _atlas(
        tmp_path / "shared",
        {
            "app/__init__.py": "",
            "app/settings.py": "FIXTURE = 'cases/one'\n",
            "tests/__init__.py": "",
            "tests/test_alpha.py": "FIXTURE = 'cases/one'\n\n\ndef test_alpha() -> None: ...\n",
        },
    )

    found = _of(shared, FindingPattern.DUPLICATED_KNOWLEDGE)
    assert len(found) == 1, "a value a test shares with production is still one fact twice"


def test_a_port_substituted_in_tests_says_so_where_the_verdict_turns_on_it(
    tmp_path: Path,
) -> None:
    """The corpus's own exception for a single implementation, and nothing measured it.

    `delay-premature-abstraction` carves out "an interface that exists so effects can be
    substituted in tests", and that is the justification a judge reaches for on almost every
    one of these candidates. The candidate said nothing about it, so the verdict came from
    somewhere other than the evidence.

    It cannot be read off the implementation count: a test double conforms structurally and
    inherits nothing, so the parse resolver emits no `implements` edge for it and the port
    still reads as having exactly one. What can be read is the method surface, which is why
    this is counted by name and says so in its limitations.
    """

    root = tmp_path / "repo"
    atlas = _atlas(
        root,
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "tests/__init__.py": "",
            "tests/test_speech.py": (
                "class RecordingSpeech:\n"
                "    def speak(self, text: str, voice: str) -> bytes: return b''\n"
                "    def close(self) -> None: return None\n\n\n"
                "def test_it_records() -> None: ...\n"
            ),
        },
    )

    port = next(
        item
        for item in _of(atlas, FindingPattern.SOLE_IMPLEMENTATION)
        if item.participants[0].qualified_name.endswith("SpeechProvider")
    )
    measured = {item.name: item.value for item in port.measurements}
    assert measured["implementations"] == 1, "the double conforms without inheriting"
    assert measured["test_doubles_offering_its_methods"] == 1

    # A class offering only part of the surface is not standing in for it.
    partial = _atlas(
        tmp_path / "partial",
        {
            "provider/__init__.py": "",
            "provider/speech.py": PORT,
            "provider/qwen.py": ADAPTER,
            "tests/__init__.py": "",
            "tests/test_speech.py": (
                "class HalfSpeech:\n"
                "    def speak(self, text: str, voice: str) -> bytes: return b''\n\n\n"
                "def test_it_records() -> None: ...\n"
            ),
        },
    )
    half = next(
        item
        for item in _of(partial, FindingPattern.SOLE_IMPLEMENTATION)
        if item.participants[0].qualified_name.endswith("SpeechProvider")
    )
    assert {i.name: i.value for i in half.measurements}[
        "test_doubles_offering_its_methods"
    ] == 0
