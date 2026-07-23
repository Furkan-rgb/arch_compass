from pathlib import Path


def test_policy_index_is_versioned_and_retrievable(runtime) -> None:
    source = Path("policies/general").resolve()
    first = runtime.policy_store.rebuild([source])
    second = runtime.policy_store.rebuild([source])
    assert first.version_id != second.version_id
    assert len(runtime.policy_store.list_policies(first.version_id)) == 15
    results = runtime.policy_store.retrieve(
        "provider-specific dependency containment",
        top_k=5,
        version_id=first.version_id,
    )
    assert results
    assert all(result.policy.id for result in results)

