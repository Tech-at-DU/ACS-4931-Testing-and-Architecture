# Testing an AI Response Cache

⭐️ **GOAL:** Write fast, deterministic pytest tests that prove a response cache hits, misses, expires, and evicts exactly when it should, without calling a real model or waiting on a real clock.

<!-- omit in toc -->
## ⏱ Agenda

- [[**5m**] Attendance &amp; Announcements](#5m-attendance--announcements)
- [[**10m**] ☀️ Warm Up](#10m-️-warm-up)
- [[**35m**] 📚 TT: Make the Cache Testable](#35m--tt-make-the-cache-testable)
- [[**10m**] 🌴 Break](#10m--break)
- [[**25m**] 💻 Activity 1: Red-Green Hit and Miss Tests](#25m--activity-1-red-green-hit-and-miss-tests)
- [[**30m**] 💻 Activity 2: Fake Clocks, Eviction, and Breaking Each Other's Cache](#30m--activity-2-fake-clocks-eviction-and-breaking-each-others-cache)
- [[**5m**] Wrap Up](#5m-wrap-up)

<!-- > -->

<!-- omit in toc -->
## 🏆 Objectives

*By the end of this session, you'll be able to&hellip;*

1. Shape a cache as a proxy or decorator so its dependencies can be swapped in tests
1. Replace a model call with `unittest.mock.Mock` or pytest's `monkeypatch` and assert hit and miss counts
1. Test time-to-live (TTL) expiry by injecting a fake clock instead of sleeping
1. Test least-recently-used (LRU) eviction order through behavior
1. Write edge-case tests for key normalization, uncached errors, and answers that must stay fresh

<!-- > -->

## [**5m**] Attendance &amp; Announcements

<!-- > -->

## [**10m**] ☀️ Warm Up

This is the model call we'll be caching. It stands in for a hosted LLM: slow, and every call is metered. It needs no API key.

```python
import time

calls = 0


def fake_llm(prompt):
    """Stand-in for a hosted model: about 1 s per call, and every call is billed."""
    global calls
    calls += 1
    time.sleep(1)
    return f"[model answer for: {prompt}]"
```

Paste it into a scratch file and answer in a comment: if a test suite has 40 tests and each one calls `fake_llm` three times, how long does the suite take? What would that number look like against a paid model?

> **📈 PROTIP:** Everything in this session wraps a real SDK client the same way. The cache only sees "a callable that takes a prompt and returns text," so the tests stay identical when the real call goes in.

<!-- > -->

## [**35m**] 📚 TT: Make the Cache Testable

Talk track (TT) for today. You already know pytest, refactoring, and a few design patterns. Today we're using all three on a response cache, which pretty much every AI app has.

### A Review Comment Worth Reading

All right, this is the kind of comment that shows up on a pull request (PR) that adds caching:

```text
review: test_cache.py::test_expiry takes 61s on CI because it calls time.sleep(61).
test_cache.py::test_hit hits the live model, so CI needs an API key and costs money per run.
Can we get these under a second and offline?
```

Both problems have the same root: the cache reaches out and grabs its dependencies (the model, the clock) instead of being handed them. Once you fix the design, the tests get a lot easier.

### Shape: Proxy or Decorator

A proxy has the same call shape as the thing it wraps. Callers can't tell the difference, which means tests can swap what's behind it. Think of it like testing a toaster with a battery pack: you don't plug into the wall every time, you just need something that heats the coils.

```python
import time
from collections import OrderedDict


def normalize(prompt):
    return " ".join(prompt.lower().split())


class ResponseCache:
    """Proxy for a model call: same call shape, plus a cache in front."""

    def __init__(self, model_call, max_size=128, ttl=300.0, clock=None):
        self.model_call = model_call
        self.max_size = max_size
        self.ttl = ttl
        self.clock = clock or time.monotonic
        self.store = OrderedDict()  # key -> (expires_at, response)
        self.hits = 0
        self.misses = 0
```

Two seams matter. `model_call` is passed in, so a test can hand it a mock. `clock` is passed in, so a test can hand it a fake. Production code never notices; it just uses the defaults.

The decorator form is a thin wrapper over the same class. Real quick:

```python
def cache_responses(**options):
    """Decorator form: @cache_responses(ttl=60) on a model-call function."""
    def wrap(model_call):
        return ResponseCache(model_call, **options)
    return wrap


@cache_responses(ttl=60)
def ask(prompt):
    return fake_llm(prompt)
```

### Mock the Model, Count the Calls

`unittest.mock.Mock` records every call. That record is how you tell a hit from a miss: a hit means the model was *not* called.

```python
from unittest.mock import Mock

model = Mock(return_value="4")
cache = ResponseCache(model)

cache("What is 2 + 2?")
cache("What is 2 + 2?")

assert model.call_count == 1
model.assert_called_once_with("What is 2 + 2?")
```

`side_effect` lets one mock play several parts. Give it a list and each call returns the next item. Put an exception in the list and that call raises it.

> **💬 ASK AUDIENCE:** Spot the bug in this test. What does it actually prove?
>
> ```python
> def test_cache_works():
>     model = Mock(return_value="4")
>     cache = ResponseCache(model)
>     assert cache("What is 2 + 2?") == "4"
>     assert cache("What is 2 + 2?") == "4"
> ```

<details>
<summary>Answer</summary>

It proves the answer comes back. It does not prove anything was cached. Honestly, a cache that calls the model every time still passes this test. Add `assert model.call_count == 1`.

</details>

### When You Can't Inject: `monkeypatch`

Sometimes the code under test calls a module-level function directly, and you don't own the constructor. pytest's `monkeypatch` fixture replaces an attribute for one test and restores it afterward:

```python
import time


def test_ttl_with_monkeypatch(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    model = Mock(return_value="sunny")
    cache = ResponseCache(model, ttl=60)  # clock is read at construction

    cache("Forecast?")
    now[0] += 61
    cache("Forecast?")
    assert model.call_count == 2
```

This works because `ResponseCache` looks up `time.monotonic` inside `__init__`. Patch the name where the code *looks it up*, at the moment it looks.

> **‼️ BE AWARE:** Write `def __init__(self, clock=time.monotonic)` and `monkeypatch` won't reach it. Python evaluates default arguments once, when the `def` runs, so the original function is already captured. Default to `None` and resolve inside the body, or inject a fake directly.

### Time Without Sleeping

For TTL tests, a fake clock is four lines and saves you every `sleep`:

```python
class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
```

`ResponseCache` calls `self.clock()`, so any callable that returns a number works. The test decides what time it is. Super handy.

> **💬 QUICK CHECK:** Predict. `ttl=60`, fake clock. Call the cache with the same prompt, `advance(59)`, call again, `advance(2)`, call again. What is `model.call_count`?

<details>
<summary>Answer</summary>

Two calls. The second call is at 59 s, still fresh, so it's a hit. The third is at 61 s, past expiry, so it's a miss and the model runs again.

</details>

### Eviction: Test Behavior, Not Internals

You could assert on `list(cache.store)`. That couples the test to one data structure. Swap `OrderedDict` for something else during a refactor and a correct cache fails its tests. Assert on what a caller sees instead: after eviction, asking for the evicted prompt calls the model again.

```text
max_size=2
"a" miss   -> store: a
"b" miss   -> store: a, b
"a" hit    -> store: b, a      (a is now most recent)
"c" miss   -> store: a, c      (b evicted)
"a" ?      -> hit, no model call
"b" ?      -> miss, model runs again
```

### Edge Cases That Bite

| Case | What the test asserts |
| --- | --- |
| `"What is 2+2?"` vs `"  what is 2+2?"` | One model call: normalization maps both to one key |
| Model raises `TimeoutError` once | The next call retries; the failure was never stored |
| "Suggest a team name" (should vary) | Passing `cacheable=False` calls the model every time and stores nothing |

Honestly, the `cacheable` flag is the simple version. A real system might decide per route or per prompt template, and the test looks the same either way.

> **💬 YOUR TURN:** What is missing from this test list? `test_hit`, `test_miss`, `test_ttl_expiry`, `test_eviction`.

<details>
<summary>Answer</summary>

A test that errors are not cached. Without it, a cache that stores a timeout (or `None`) passes every test and then serves that failure for the full TTL.

</details>

<!-- > -->

## [**10m**] 🌴 Break

<!-- > -->

## [**25m**] 💻 Activity 1: Red-Green Hit and Miss Tests

> **✅ DONE WHEN:** you have seen `3 failed, 1 passed` against the stub, then `4 passed` against your implementation.

1. Make a folder `cache_tests/`. Inside it, paste this stub as `response_cache.py`. It has the right shape and no caching yet:

    ```python
    def normalize(prompt):
        return " ".join(prompt.lower().split())


    class ResponseCache:
        def __init__(self, model_call, max_size=128, ttl=300.0, clock=None):
            self.model_call = model_call
            self.hits = 0
            self.misses = 0

        def __call__(self, prompt, cacheable=True):
            return self.model_call(prompt)  # no cache yet


    def cache_responses(**options):
        def wrap(model_call):
            return ResponseCache(model_call, **options)
        return wrap
    ```

1. Paste these tests as `test_hit_miss.py`:

    ```python
    from unittest.mock import Mock

    import pytest

    from response_cache import ResponseCache


    def test_first_call_is_a_miss():
        model = Mock(return_value="4")
        cache = ResponseCache(model)

        assert cache("What is 2 + 2?") == "4"
        model.assert_called_once_with("What is 2 + 2?")
        assert (cache.hits, cache.misses) == (0, 1)


    def test_repeat_prompt_is_a_hit():
        model = Mock(return_value="4")
        cache = ResponseCache(model)

        cache("What is 2 + 2?")
        cache("What is 2 + 2?")

        assert model.call_count == 1
        assert (cache.hits, cache.misses) == (1, 1)


    def test_whitespace_and_case_share_a_key():
        model = Mock(return_value="4")
        cache = ResponseCache(model)

        cache("What is 2 + 2?")
        cache("  what is 2 +   2?")

        assert model.call_count == 1


    def test_errors_are_not_cached():
        model = Mock(side_effect=[TimeoutError("model timed out"), "4"])
        cache = ResponseCache(model)

        with pytest.raises(TimeoutError):
            cache("What is 2 + 2?")
        assert cache("What is 2 + 2?") == "4"
        assert model.call_count == 2
    ```

1. Run `pytest -q`. Read the three failures before you touch any code. The error test passes already. Write one sentence on why.
1. Make the tests pass. Add a `self.store = {}` dict, count misses, call the model only on a miss, and store the response *after* the call returns.
1. Run `pytest -q` until you see `4 passed`. Stuck for more than ten minutes? Compare with this:

    <details>
    <summary>Reference Implementation</summary>

    ```python
    def __call__(self, prompt, cacheable=True):
        if not cacheable:
            return self.model_call(prompt)
        key = normalize(prompt)
        if key in self.store:
            self.hits += 1
            return self.store[key]
        self.misses += 1
        response = self.model_call(prompt)  # an exception skips the store
        self.store[key] = response
        return response
    ```

    </details>

> **‼️ WATCH OUT:** Don't wrap the model call in `try/except` and store a fallback. The error test exists to catch exactly that.

<!-- > -->

## [**30m**] 💻 Activity 2: Fake Clocks, Eviction, and Breaking Each Other's Cache

> **✅ DONE WHEN:** `pytest -q` shows `9 passed`, and your mutation table below has at least three rows.

1. Paste these tests as `test_ttl_lru.py`. Run them. Three should fail against your Activity 1 cache.

    ```python
    import time
    from unittest.mock import Mock

    from response_cache import ResponseCache, cache_responses


    class FakeClock:
        def __init__(self, start=1000.0):
            self.now = start

        def __call__(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds


    def test_entry_expires_after_ttl():
        clock = FakeClock()
        model = Mock(return_value="sunny")
        cache = ResponseCache(model, ttl=60, clock=clock)

        cache("Forecast for Chicago?")
        clock.advance(59)
        cache("Forecast for Chicago?")
        assert model.call_count == 1

        clock.advance(2)
        cache("Forecast for Chicago?")
        assert model.call_count == 2


    def test_lru_evicts_least_recently_used():
        model = Mock(side_effect=lambda prompt: prompt.upper())
        cache = ResponseCache(model, max_size=2)

        cache("a")
        cache("b")
        cache("a")  # a is now the most recent
        cache("c")  # over the cap: b goes
        assert model.call_count == 3

        cache("a")
        assert model.call_count == 3  # still cached
        cache("b")
        assert model.call_count == 4  # evicted, so the model ran again


    def test_non_cacheable_prompt_always_calls_model():
        model = Mock(side_effect=["Zephyr", "Juniper"])
        cache = ResponseCache(model)

        first = cache("Suggest a team name", cacheable=False)
        second = cache("Suggest a team name", cacheable=False)

        assert (first, second) == ("Zephyr", "Juniper")
        assert len(cache.store) == 0


    def test_ttl_with_monkeypatch(monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(time, "monotonic", lambda: now[0])
        model = Mock(return_value="sunny")
        cache = ResponseCache(model, ttl=60)  # clock is read at construction

        cache("Forecast?")
        now[0] += 61
        cache("Forecast?")
        assert model.call_count == 2


    def test_decorator_form():
        calls = []

        @cache_responses(max_size=8)
        def ask(prompt):
            calls.append(prompt)
            return "ok"

        ask("hi")
        ask("hi")
        assert len(calls) == 1
        assert ask.hits == 1
    ```

1. Upgrade `ResponseCache` until all nine tests pass. Store `(expires_at, response)` in an `OrderedDict`. A hit needs `self.clock() < expires_at` and a `move_to_end(key)`. After each store, `popitem(last=False)` while over `max_size`. Keep `self.clock = clock or time.monotonic` in `__init__`.
1. Trade test files with a teammate. Each of you writes a broken copy of your own `response_cache.py` that breaks exactly one rule, then runs the other person's tests against it. Some ideas:
    - Drop the `move_to_end` call on a hit
    - Change `popitem(last=False)` to `popitem()`
    - Change `<` to `<=` in the expiry check
    - Store `None` when the model raises
1. Record every attempt in a mutation table:

    ```text
    | Mutation                      | Caught? | By which test             |
    | ----------------------------- | ------- | ------------------------- |
    | no move_to_end on hit         |         |                           |
    ```

1. For any mutation that survived, write the test that would have caught it, and confirm it fails against the broken copy and passes against the real one.

> **📈 TIP:** No teammate free? Work the same loop solo: apply each idea from step 3 to a copy of your own cache, run your own suite, and fill in the table. Post the table in the team thread when you can; anyone can pick it up later and try to beat it.

<!-- > -->

## [**5m**] Wrap Up

- Push `cache_tests/` with both test files and your mutation table.
- Post a checkpoint in the team thread:

    ```text
    Built:
    Verified:
    Blocked by:
    Next:
    ```

- If a test is flaky, look for a real clock or a real sleep first.

<!-- > -->

## Additional Resources

1. [Python docs: `unittest.mock`](https://docs.python.org/3/library/unittest.mock.html) (see [`call_count`](https://docs.python.org/3/library/unittest.mock.html#unittest.mock.Mock.call_count) and [`side_effect`](https://docs.python.org/3/library/unittest.mock.html#unittest.mock.Mock.side_effect))
1. [pytest docs: How to monkeypatch/mock modules and environments](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
1. [pytest docs: Assertions about expected exceptions](https://docs.pytest.org/en/stable/how-to/assert.html#assertions-about-expected-exceptions)
1. [Python docs: `collections.OrderedDict`](https://docs.python.org/3/library/collections.html#collections.OrderedDict)
1. [Python docs: `time.monotonic`](https://docs.python.org/3/library/time.html#time.monotonic)
1. [Python docs: `functools.lru_cache`](https://docs.python.org/3/library/functools.html#functools.lru_cache) (the built-in cache, for comparison)
1. [Refactoring.Guru: Proxy pattern](https://refactoring.guru/design-patterns/proxy)

<details>
<summary>For Curriculum Authors</summary>

## For Curriculum Authors

### In Class

- MVP (15 minutes or less): get `test_hit_miss.py` from red to green and post the checkpoint paste (Built / Verified / Blocked by / Next).
- Breakouts of 2–3 for Activity 2 so the test trade has a partner. Odd one out takes the solo path in the 📈 callout; it counts the same as the paired path.
- After Activity 1, ask one room to explain why the error test passes against the stub (the stub never stores anything, so it can't store an error).
- Anyone who missed the session can do both activities alone and post the checkpoint and mutation table later. No extra write-up needed.

### Facilitator Notes

- Live-code the spot-the-bug pulse and the `FakeClock` only. Then get out of the way.
- The `<` to `<=` mutation survives the provided suite on purpose. The tests check 59 s and 61 s, never exactly 60 s. Rooms that find it should write this test:

    ```python
    def test_entry_expires_exactly_at_ttl():
        clock = FakeClock()
        model = Mock(return_value="sunny")
        cache = ResponseCache(model, ttl=60, clock=clock)

        cache("Forecast?")
        clock.advance(60)
        cache("Forecast?")
        assert model.call_count == 2
    ```

- The other three mutation ideas are each caught by exactly one provided test. Verified against Python 3.13 and pytest 9.
- Reference implementation for Activity 2:

    ```python
    def __call__(self, prompt, cacheable=True):
        if not cacheable:
            return self.model_call(prompt)
        key = normalize(prompt)
        entry = self.store.get(key)
        if entry is not None and self.clock() < entry[0]:
            self.store.move_to_end(key)
            self.hits += 1
            return entry[1]
        self.misses += 1
        response = self.model_call(prompt)  # an exception skips the store
        self.store[key] = (self.clock() + self.ttl, response)
        self.store.move_to_end(key)
        while len(self.store) > self.max_size:
            self.store.popitem(last=False)
        return response
    ```

    It also needs `self.store = OrderedDict()`, `self.max_size`, `self.ttl`, and `self.clock = clock or time.monotonic` in `__init__`, as shown in TT.

### Expert Follow-Ups

- Thread safety: two requests miss on the same key at once and both call the model. How would you test for that?
- Property-based testing (Hypothesis) can generate prompt sequences and compare the cache against a simple reference model.

</details>
