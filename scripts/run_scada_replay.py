import argparse
from pathlib import Path
from workflows.scada_replay_engine import ScadaReplayEngine, ReplayConfig, WORKSPACE

def main():
    parser = argparse.ArgumentParser(description="SCADA Replay Engine CLI")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--sqlite", required=True)
    args = parser.parse_args()
    
    cfg = ReplayConfig(
        case_id=args.case_id,
        sqlite_path=Path(args.sqlite),
        scenario_id="default_scenario",
        replay_speed=1.0,
        quality_code="GOOD",
        max_events=1000
    )
    
    engine = ScadaReplayEngine(cfg)
    summary_path = WORKSPACE / f"cases/{args.case_id}/contracts/scada_replay_summary.json"
    stream_path = WORKSPACE / f"cases/{args.case_id}/contracts/scada_stream.jsonl"
    
    summary = engine.run(summary_path, stream_path)
    
    print(f"Replay completed.")
    print(f"Records loaded: {summary['records_loaded']}")
    print(f"Messages emitted: {summary['messages_emitted']}")
    print(f"Stream written to: {summary['stream_path']}")
    
    with open(stream_path, 'r') as f:
        print("First 3 messages:")
        for _ in range(3):
            line = f.readline()
            if line:
                print(line.strip())

if __name__ == "__main__":
    main()