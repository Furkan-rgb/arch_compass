"""Getting a repository onto the machine and keeping track of which one it is.

`checkout.py` clones, `sources.py` fetches an archive where git is not wanted, and
`service.py` indexes what either produced. `lineage.py` is the durable identity a
repository and its branches carry between runs, `records.py` the validated records the rest
of the system is handed, and `adapters/` the git command line and the HTTPS fetcher.
"""
