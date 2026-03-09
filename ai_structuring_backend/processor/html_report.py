"""
HTML Report Generator for Classification Results
Generates a user-friendly HTML view instead of/alongside JSON
"""

from pathlib import Path
from datetime import datetime
from typing import Optional
import json

def generate_html_report(
    document_name: str,
    classifications: list[dict],
    filtered_results: dict,
    output_path: Path
) -> Path:
    """
    Generate an interactive HTML report of classification results.
    """
    summary = filtered_results.get("summary", {})
    flagged = filtered_results.get("needs_review", [])
    
    # Calculate statistics
    total = summary.get("total_paragraphs", len(classifications))
    auto_applied = summary.get("auto_applied", 0)
    needs_review = summary.get("needs_review", 0)
    auto_pct = summary.get("auto_apply_percentage", 0)
    
    # Group by tag for statistics
    tag_counts = {}
    for c in classifications:
        tag = c.get("tag", "Unknown")
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    # Sort tags by count
    sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Classification Results - {document_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .card {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            margin-bottom: 20px;
            overflow: hidden;
        }}
        
        .card-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 30px;
        }}
        
        .card-header h1 {{
            font-size: 1.8rem;
            margin-bottom: 5px;
        }}
        
        .card-header p {{
            opacity: 0.9;
            font-size: 0.95rem;
        }}
        
        .card-body {{
            padding: 25px 30px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }}
        
        .stat-box {{
            text-align: center;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 12px;
        }}
        
        .stat-box .value {{
            font-size: 2.5rem;
            font-weight: bold;
            color: #667eea;
        }}
        
        .stat-box .label {{
            color: #666;
            font-size: 0.85rem;
            margin-top: 5px;
        }}
        
        .stat-box.success .value {{ color: #28a745; }}
        .stat-box.warning .value {{ color: #ffc107; }}
        .stat-box.danger .value {{ color: #dc3545; }}
        
        .progress-bar {{
            height: 30px;
            background: #e9ecef;
            border-radius: 15px;
            overflow: hidden;
            margin: 20px 0;
        }}
        
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #28a745, #20c997);
            border-radius: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            transition: width 0.5s ease;
        }}
        
        h2 {{
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }}
        
        .tag-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 10px;
            margin-bottom: 20px;
        }}
        
        .tag-item {{
            background: #f0f0f0;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            font-size: 0.85rem;
        }}
        
        .tag-item .tag-name {{
            font-weight: bold;
            color: #667eea;
        }}
        
        .tag-item .tag-count {{
            color: #666;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        
        th {{
            background: #667eea;
            color: white;
            font-weight: 600;
            position: sticky;
            top: 0;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .confidence {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: bold;
        }}
        
        .confidence.high {{
            background: #d4edda;
            color: #155724;
        }}
        
        .confidence.medium {{
            background: #fff3cd;
            color: #856404;
        }}
        
        .confidence.low {{
            background: #f8d7da;
            color: #721c24;
        }}
        
        .tag-badge {{
            display: inline-block;
            padding: 4px 12px;
            background: #667eea;
            color: white;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 500;
        }}
        
        .text-preview {{
            max-width: 400px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: #666;
            font-size: 0.9rem;
        }}
        
        .alternatives {{
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }}
        
        .alt-tag {{
            padding: 2px 8px;
            background: #e9ecef;
            border-radius: 10px;
            font-size: 0.75rem;
            color: #666;
        }}
        
        .zone-violation {{
            display: inline-block;
            padding: 2px 6px;
            background: #dc3545;
            color: white;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: bold;
            margin-right: 5px;
            cursor: help;
        }}
        
        .fallback-used {{
            display: inline-block;
            padding: 2px 6px;
            background: #17a2b8;
            color: white;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: bold;
            margin-right: 5px;
            cursor: help;
        }}
        
        tr.zone-error {{
            background-color: #fff5f5;
        }}
        
        tr.zone-error:hover {{
            background-color: #ffe0e0;
        }}
        
        tr.fallback-row {{
            background-color: #f0f9ff;
        }}
        
        tr.fallback-row:hover {{
            background-color: #e0f2ff;
        }}
        
        tr.zone-error.fallback-row {{
            background-color: #fff0f5;
        }}
        
        .filter-tabs {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }}
        
        .filter-tab {{
            padding: 10px 20px;
            background: #e9ecef;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.3s;
        }}
        
        .filter-tab:hover {{
            background: #dee2e6;
        }}
        
        .filter-tab.active {{
            background: #667eea;
            color: white;
        }}
        
        .scrollable {{
            max-height: 500px;
            overflow-y: auto;
        }}
        
        .timestamp {{
            color: #999;
            font-size: 0.85rem;
            margin-top: 20px;
            text-align: center;
        }}
        
        .search-box {{
            width: 100%;
            padding: 12px 20px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            margin-bottom: 15px;
        }}
        
        .search-box:focus {{
            outline: none;
            border-color: #667eea;
        }}
        
        .no-results {{
            text-align: center;
            padding: 40px;
            color: #999;
        }}
        
        @media (max-width: 768px) {{
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            
            .text-preview {{
                max-width: 200px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header Card -->
        <div class="card">
            <div class="card-header">
                <h1>📄 Classification Results</h1>
                <p>{document_name}</p>
            </div>
            <div class="card-body">
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="value">{total}</div>
                        <div class="label">Total Paragraphs</div>
                    </div>
                    <div class="stat-box success">
                        <div class="value">{auto_applied}</div>
                        <div class="label">Auto-Applied (≥85%)</div>
                    </div>
                    <div class="stat-box warning">
                        <div class="value">{needs_review}</div>
                        <div class="label">Needs Review (&lt;85%)</div>
                    </div>
                    <div class="stat-box">
                        <div class="value">{len(tag_counts)}</div>
                        <div class="label">Unique Tags Used</div>
                    </div>
                </div>
                
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {auto_pct}%">
                        {auto_pct:.1f}% Auto-Applied
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Tag Distribution -->
        <div class="card">
            <div class="card-body">
                <h2>📊 Tag Distribution</h2>
                <div class="tag-grid">
'''
    
    # Add tag distribution
    for tag, count in sorted_tags[:20]:
        html += f'''                    <div class="tag-item">
                        <div class="tag-name">{tag}</div>
                        <div class="tag-count">{count} ({count*100/total:.1f}%)</div>
                    </div>
'''
    
    html += '''                </div>
            </div>
        </div>
        
        <!-- Flagged Items (Needs Review) -->
        <div class="card">
            <div class="card-body">
                <h2>⚠️ Items Needing Review ({} items)</h2>
'''.format(len(flagged))
    
    if flagged:
        html += '''                <input type="text" class="search-box" placeholder="Search by paragraph ID, tag, or text..." onkeyup="filterTable(this, 'flagged-table')">
                <div class="scrollable">
                    <table id="flagged-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Suggested Tag</th>
                                <th>Confidence</th>
                                <th>Text Preview</th>
                                <th>Reasoning</th>
                                <th>Alternatives</th>
                            </tr>
                        </thead>
                        <tbody>
'''
        for item in flagged:
            conf = item.get("confidence", 0)
            conf_class = "low" if conf < 70 else "medium"
            text = item.get("original_text", "")[:80]
            alts = item.get("alternatives", [])
            
            # Check for zone violation
            zone_violation = item.get("zone_violation", False)
            zone_indicator = '<span class="zone-violation" title="Style not valid for this zone">⚠️ ZONE</span> ' if zone_violation else ''
            
            # Check for fallback usage
            fallback_used = item.get("fallback_used", False)
            fallback_indicator = '<span class="fallback-used" title="Re-analyzed by Flash model">🔄 FLASH</span> ' if fallback_used else ''
            
            # Add zone suggestions to alternatives if present
            zone_suggestions = item.get("zone_suggestions", [])
            if zone_suggestions:
                alts = zone_suggestions + alts
            
            # Add original tag to reasoning if changed by fallback
            original_tag = item.get("original_tag")
            original_conf = item.get("original_confidence")
            fallback_note = ""
            if fallback_used and original_tag:
                fallback_note = f" (was: {original_tag} {original_conf}%)"
            
            html += f'''                            <tr class="{'zone-error' if zone_violation else ''} {'fallback-row' if fallback_used else ''}">
                                <td><strong>#{item.get("id", "?")}</strong></td>
                                <td>{zone_indicator}{fallback_indicator}<span class="tag-badge">{item.get("tag", "?")}</span>{fallback_note}</td>
                                <td><span class="confidence {conf_class}">{conf}%</span></td>
                                <td class="text-preview" title="{item.get("original_text", "")}">{text}...</td>
                                <td>{item.get("reasoning", "-")}</td>
                                <td class="alternatives">
'''
            for alt in alts[:3]:
                html += f'                                    <span class="alt-tag">{alt}</span>\n'
            html += '''                                </td>
                            </tr>
'''
        html += '''                        </tbody>
                    </table>
                </div>
'''
    else:
        html += '''                <div class="no-results">
                    <h3>✅ All items auto-applied!</h3>
                    <p>No paragraphs require manual review.</p>
                </div>
'''
    
    html += '''            </div>
        </div>
        
        <!-- All Classifications -->
        <div class="card">
            <div class="card-body">
                <h2>📋 All Classifications</h2>
                <div class="filter-tabs">
                    <button class="filter-tab active" onclick="filterByConfidence('all', this)">All</button>
                    <button class="filter-tab" onclick="filterByConfidence('high', this)">High (≥95%)</button>
                    <button class="filter-tab" onclick="filterByConfidence('medium', this)">Medium (85-94%)</button>
                    <button class="filter-tab" onclick="filterByConfidence('low', this)">Low (&lt;85%)</button>
                </div>
                <input type="text" class="search-box" placeholder="Search classifications..." onkeyup="filterTable(this, 'all-table')">
                <div class="scrollable">
                    <table id="all-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Tag</th>
                                <th>Confidence</th>
                                <th>Reasoning</th>
                            </tr>
                        </thead>
                        <tbody>
'''
    
    for c in classifications:
        conf = c.get("confidence", 0)
        if conf >= 95:
            conf_class = "high"
        elif conf >= 85:
            conf_class = "medium"
        else:
            conf_class = "low"
        
        html += f'''                            <tr data-confidence="{conf_class}">
                                <td><strong>#{c.get("id", "?")}</strong></td>
                                <td><span class="tag-badge">{c.get("tag", "?")}</span></td>
                                <td><span class="confidence {conf_class}">{conf}%</span></td>
                                <td>{c.get("reasoning", "-")}</td>
                            </tr>
'''
    
    html += f'''                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <p class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>
    
    <script>
        function filterTable(input, tableId) {{
            const filter = input.value.toLowerCase();
            const table = document.getElementById(tableId);
            const rows = table.getElementsByTagName('tr');
            
            for (let i = 1; i < rows.length; i++) {{
                const cells = rows[i].getElementsByTagName('td');
                let found = false;
                
                for (let j = 0; j < cells.length; j++) {{
                    if (cells[j].textContent.toLowerCase().includes(filter)) {{
                        found = true;
                        break;
                    }}
                }}
                
                rows[i].style.display = found ? '' : 'none';
            }}
        }}
        
        function filterByConfidence(level, btn) {{
            // Update active tab
            document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
            btn.classList.add('active');
            
            // Filter rows
            const table = document.getElementById('all-table');
            const rows = table.getElementsByTagName('tr');
            
            for (let i = 1; i < rows.length; i++) {{
                const conf = rows[i].getAttribute('data-confidence');
                
                if (level === 'all' || conf === level) {{
                    rows[i].style.display = '';
                }} else {{
                    rows[i].style.display = 'none';
                }}
            }}
        }}
    </script>
</body>
</html>
'''
    
    # Write HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return output_path


# Example usage
if __name__ == "__main__":
    # Sample data
    sample_classifications = [
        {"id": 1, "tag": "CN", "confidence": 99},
        {"id": 2, "tag": "CT", "confidence": 98},
        {"id": 3, "tag": "H1", "confidence": 96},
        {"id": 4, "tag": "TXT-FLUSH", "confidence": 72, "reasoning": "Could be INTRO"},
        {"id": 5, "tag": "TXT", "confidence": 94},
        {"id": 6, "tag": "BL-FIRST", "confidence": 88},
        {"id": 7, "tag": "BL-MID", "confidence": 65, "reasoning": "Position unclear"},
        {"id": 8, "tag": "BL-LAST", "confidence": 91},
    ]
    
    sample_filtered = {
        "summary": {
            "total_paragraphs": 8,
            "auto_applied": 6,
            "needs_review": 2,
            "auto_apply_percentage": 75.0,
        },
        "needs_review": [
            {
                "id": 4,
                "tag": "TXT-FLUSH",
                "confidence": 72,
                "original_text": "This chapter explores the fundamentals of cellular immunotherapy...",
                "reasoning": "Could be INTRO based on italic formatting",
                "alternatives": ["INTRO", "TXT"],
            },
            {
                "id": 7,
                "tag": "BL-MID",
                "confidence": 65,
                "original_text": "• Second bullet point in the list",
                "reasoning": "Position unclear - could be FIRST or MID",
                "alternatives": ["BL-FIRST", "BL-LAST"],
            },
        ],
    }
    
    output = generate_html_report(
        "test_chapter.docx",
        sample_classifications,
        sample_filtered,
        Path("/tmp/test_report.html")
    )
    print(f"Generated: {output}")
