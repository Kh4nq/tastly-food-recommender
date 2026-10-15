"""Run from project root: python demo_hard_filter.py --processed-dir data/processed"""
import argparse
from retrieval.hard_filter import load_tables, filter_candidates

p = argparse.ArgumentParser()
p.add_argument('--processed-dir', default='data/processed')
p.add_argument('--lat', type=float, required=True, help='Your demo latitude')
p.add_argument('--lon', type=float, required=True, help='Your demo longitude')
p.add_argument('--budget', type=int, default=100_000)
p.add_argument('--radius', type=float, default=5)
p.add_argument('--vegetarian', action='store_true')
a = p.parse_args()
restaurants, dishes, menus = load_tables(a.processed_dir)
state = {'location': [a.lat, a.lon], 'hard_constraints': {'budget_max': a.budget, 'max_distance_km': a.radius, **({'vegetarian': True} if a.vegetarian else {})}}
candidates = filter_candidates(restaurants, dishes, menus, state)
print(f'Valid menu candidates: {len(candidates):,}')
print(candidates.head(10).to_string(index=False))
print('NOTE: prices are synthetic estimates, not verified menus.')
