# cobot_db

Supabase persistence layer for `cobot2`. Two domains:

| Table             | Purpose                                                |
| ----------------- | ------------------------------------------------------ |
| `exception_logs`  | Per-task failure records — `cluster_push` and `verification_round` only |
| `inventory`       | Current stock per nut type (4 rows, one per class)     |
| `inventory_logs`  | Append-only ledger of every stock change               |

Stock writes go through a single `update_inventory_atomic(...)` RPC so the
`UPDATE inventory` and `INSERT inventory_logs` happen in one server-side
transaction (no race on `current_stock`).

## Layout

```
cobot_db/
├── package.xml / setup.py / setup.cfg / resource/cobot_db   # ROS2 ament_python skeleton
├── sql/init.sql                                             # DDL + RPC + RLS + seed
├── cobot_db/
│   ├── __init__.py
│   ├── cobot_db_manager.py                                  # CobotDbManager class
│   └── integration_example.py                               # Cluster push + verification demo
├── .env.example                                             # SUPABASE_URL / SUPABASE_KEY template
└── README.md
```

## Setup

### 1) Apply the schema

Open Supabase Dashboard → **SQL Editor** → paste `sql/init.sql` → **Run**.
Idempotent — re-running won't reset stock that's already been picked.

### 2) Configure credentials

```bash
cd cobot2/cobot_db
cp .env.example .env
# edit .env with the real publishable key from
# Supabase Dashboard -> Project Settings -> API
```

### 3) Install Python dependencies

`supabase-py` is not in apt. Install via pip into the same Python that
runs your ROS nodes:

```bash
pip install 'supabase>=2.0' 'python-dotenv>=1.0'
```

### 4) Build (optional — only needed if you want `ros2 run`)

```bash
cd ~/cobot_ws
colcon build --packages-select cobot_db
source install/setup.bash
ros2 run cobot_db cobot_db_example
```

You can also just run the example directly:

```bash
python -m cobot_db.integration_example
```

## API

```python
from cobot_db import CobotDbManager

db = CobotDbManager()  # reads .env from CWD; or pass url=/key= explicitly

# 1) Log a task-specific exception
db.log_robot_exception(
    task_name="cluster_push",      # or "verification_round" — only these two
    state="ENTRY_HIT",             # free-form short tag
    error_code=1,
    error_msg="no clean push direction",
    target_class="cashew",
    target_xyz={"x": 450.0, "y": -50.0, "z": 65.0},
    robot_pose=None,               # or {"j1": ..., "j6": ...}
)

# 2) Atomically deduct (or refill) stock + write a ledger row
row = db.update_inventory(nut_type="almond", amount=-1, reason="primary_pick_success")
print(row.current_stock)           # new stock after the change

# 3) Read inventory
for row in db.get_inventory():
    print(row.nut_type, row.current_stock)
```

## Where to call from `cobot_task_manager`

See `cobot_db/integration_example.py` for the full picture. Summary:

| Call site in `task_manager_node._process_order_book`         | Hook                                               |
| ------------------------------------------------------------ | -------------------------------------------------- |
| `choose_cluster_plan(...)` returns `None`                    | `log_robot_exception(task_name='cluster_push', state='ENTRY_HIT', ...)` |
| `_send_cluster_push_goal(...)` returns falsy                 | `log_robot_exception(task_name='cluster_push', state='MOTION_FAIL', ...)` |
| Primary pick action returns `success=True`                   | `update_inventory(nut_type=cls, amount=-1, reason='primary_pick_success')` |
| Verification round computes `remaining[cls] > 0`             | `log_robot_exception(task_name='verification_round', state='COUNT_MISMATCH', ...)` |
| Correction pick returns `success=True`                       | `update_inventory(nut_type=cls, amount=-1, reason='verify_pick_success_round_N')` |
| Correction pick returns `success=False` after retries        | `log_robot_exception(task_name='verification_round', state='MOTION_FAIL', ...)` |

## Security model

- The robot ships with the **publishable** (anon) key only. Real protection
  is the RLS policies in `sql/init.sql`:
  - `inventory` and `inventory_logs` — read-only for anon. The only way
    to mutate them is the `update_inventory_atomic` RPC, which is
    `SECURITY DEFINER` and validates inputs server-side.
  - `exception_logs` — anon may `INSERT` and `SELECT`. The robot writes
    its own failure records directly; the RLS policy makes this safe
    because there's no privileged data in this table.
- Never put the `service_role` key on the robot. There's no need for it
  with the RPC + RLS setup above.

## Adding a new exception task type

The `task_name` column has a `CHECK` constraint that allows only two
values today. To add a third:

1. Edit `sql/init.sql` — add the new value to the `CHECK (task_name in ...)`
   clause.
2. Apply with `ALTER TABLE public.exception_logs DROP CONSTRAINT exception_logs_task_name_check; ALTER TABLE ... ADD CONSTRAINT ... CHECK (...);` in the SQL editor.
3. Edit `cobot_db_manager.py` — add the new value to `_VALID_TASKS`.

This is intentional friction: the constraint is what guarantees you can
group/aggregate by `task_name` without surprises.
