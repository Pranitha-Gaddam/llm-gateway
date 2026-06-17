# app/templates/dashboard.py

def render_dashboard_html(data: dict) -> str:
    """
    Compiles a polished, responsive developer interface for gateway telemetry.
    """
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>⚡ LLM Gateway Metrics Dashboard</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0d1117; color: #c9d1d9; margin: 0; padding: 40px; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            h1 {{ color: #f0f6fc; border-bottom: 1px solid #21262d; padding-bottom: 15px; margin-bottom: 30px; font-weight: 500; display: flex; align-items: center; gap: 10px; }}
            .grid {{ display: grid; grid-template-columns: repeat(3, 100%%); gap: 20px; margin-bottom: 30px; }}
            @media (min-width: 768px) {{ .grid {{ grid-template-columns: repeat(3, 1fr); }} }}
            .card {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 24px; position: relative; }}
            .card-title {{ color: #8b949e; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; font-weight: 600; }}
            .card-value {{ font-size: 28px; font-weight: bold; color: #58a6ff; font-family: monospace; }}
            .card-sub {{ font-size: 12px; color: #8b949e; margin-top: 6px; }}
            .bar-container {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 24px; margin-bottom: 30px; }}
            .bar-title {{ font-size: 15px; margin-bottom: 15px; font-weight: 500; color: #f0f6fc; }}
            .progress-bar {{ display: flex; height: 24px; border-radius: 4px; overflow: hidden; background-color: #21262d; }}
            .segment {{ height: 100%%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; color: white; transition: width 0.3s ease; }}
            .seg-exact {{ background-color: #2ea44f; }}
            .seg-semantic {{ background-color: #986ee2; }}
            .seg-miss {{ background-color: #6e7681; }}
            .legend {{ display: flex; gap: 20px; margin-top: 15px; font-size: 13px; }}
            .legend-item {{ display: flex; align-items: center; gap: 6px; color: #8b949e; }}
            .dot {{ width: 10px; height: 10px; border-radius: 50%%; display: inline-block; }}
            .highlight-green {{ color: #3fb950 !important; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚡ LLM Proxy Optimization Dashboard</h1>
            
            <div class="bar-container">
                <div class="bar-title">Architectural Request Topology Distribution — <span class="highlight-green">Efficiency Rate: {data['efficiency_rate']}%%</span></div>
                <div class="progress-bar">
                    <div class="segment seg-exact" style="width: {data['exact_pct']}%%" title="Exact Cache Match">{data['exact_pct']}%%</div>
                    <div class="segment seg-semantic" style="width: {data['semantic_pct']}%%" title="Semantic Vector Match">{data['semantic_pct']}%%</div>
                    <div class="segment seg-miss" style="width: {data['miss_pct']}%%" title="Live Cloud Fallback">{data['miss_pct']}%%</div>
                </div>
                <div class="legend">
                    <div class="legend-item"><span class="dot" style="background-color: #2ea44f;"></span> Tier 1: Global Exact ({data['exact_hits']})</div>
                    <div class="legend-item"><span class="dot" style="background-color: #986ee2;"></span> Tier 2: Semantic Vector ({data['semantic_hits']})</div>
                    <div class="legend-item"><span class="dot" style="background-color: #6e7681;"></span> Live Upstream Misses ({data['cache_misses']})</div>
                </div>
            </div>

            <div class="grid">
                <div class="card">
                    <div class="card-title">Compute Acceleration</div>
                    <div class="card-value" style="color: #bc8cff;">{data['speed_multiplier']}x</div>
                    <div class="card-sub">Faster routing execution vs live cloud handshakes</div>
                </div>
                <div class="card">
                    <div class="card-title">Resource Conservation</div>
                    <div class="card-value" style="color: #3fb950;">${data['total_cost_saved']:,.4f}</div>
                    <div class="card-sub">Estimated upstream infrastructure costs saved</div>
                </div>
                <div class="card">
                    <div class="card-title">Cache Proxy Latency</div>
                    <div class="card-value" style="color: #ffa657;">{data['avg_cached'] * 1000:,.1f}ms</div>
                    <div class="card-sub">Avg transaction speed on memory collection hits</div>
                </div>
            </div>

            <div class="grid" style="grid-template-columns: 1fr 1fr;">
                <div class="card">
                    <div class="card-title">Average Live Upstream Overhead</div>
                    <div class="card-value" style="font-size: 22px; color: #f85149;">{data['avg_live']:,.3f} sec</div>
                    <div class="card-sub">Network latency spent during live provider execution</div>
                </div>
                <div class="card">
                    <div class="card-title">Cumulative CPU Processing Saved</div>
                    <div class="card-value" style="font-size: 22px; color: #bc8cff;">{data['total_latency_saved']:,.2f}s</div>
                    <div class="card-sub">Total event loop thread execution time protected</div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """