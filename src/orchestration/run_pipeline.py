"""Pipeline entrypoint — wires extract -> transform -> load.

Phase 3 target: wrap this in an APScheduler job for daily runs, and
add data quality checks (e.g. alert on negative/missing close prices).
"""


def run() -> None:
    print("Pipeline stub — implement extract/transform/load calls here.")


if __name__ == "__main__":
    run()
