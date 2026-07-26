import type { RepositorySummary } from "./types";

/**
 * One entry per repository, carrying its most recent atlas.
 *
 * Indexing the same path twice produces two immutable versions, and both are listed. A
 * picker that showed both would offer a choice nobody wants to make: the older atlas is
 * evidence about a repository as it used to be, and a review runs against the current
 * one. The listing arrives newest first, so the first row for a root path is its latest.
 */
export function latestPerRepository(repositories: RepositorySummary[]): RepositorySummary[] {
  return repositories.filter(
    (repository, index, all) =>
      all.findIndex((item) => item.root_path === repository.root_path) === index,
  );
}
