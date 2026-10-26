"""Developer-only, live API classification probe; no DB/RAG access or login."""

import argparse
import sys

from backend.planner.service import Planner, PlannerInputError, PlannerUnavailable
from backend.policy.engine import AIS, ROLES, PolicyContext


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--question', required=True)
    parser.add_argument('--role', choices=sorted(ROLES), required=True)
    parser.add_argument('--day', type=int, choices=range(1, 7), required=True)
    parser.add_argument('--character-id', choices=sorted(AIS), required=True)
    args = parser.parse_args()
    # Explicit synthetic state for model evaluation only. No credentials or
    # actual records are obtained from these IDs and no authorization is tested.
    context = PolicyContext(1, 1, 1, args.role, args.day, args.character_id, 'game-data')
    try:
        result = Planner.from_environment().plan(args.question, context)
    except (PlannerInputError, PlannerUnavailable) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(result.model_dump_json())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
