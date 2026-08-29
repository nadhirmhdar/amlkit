"""UBO ownership diagram generation using Graphviz."""

from __future__ import annotations

import html
import logging
import sqlite3
import graphviz

log = logging.getLogger("amlkit.diagram")


def generate_ubo_diagram(conn: sqlite3.Connection, customer_id: int, org_id: int) -> str | None:
    """Generate SVG representation of UBO ownership/control structure.
    
    Returns raw SVG string, or None if no diagram can be generated.
    """
    # Fetch customer
    customer = conn.execute(
        "SELECT id, full_name, customer_type FROM customers WHERE id = ? AND org_id = ?",
        (customer_id, org_id)
    ).fetchone()
    
    if not customer:
        return None

    # Fetch UBOs/directors
    ubos = conn.execute(
        """SELECT person_name, ownership_pct, control_type, is_ubo 
           FROM ubo_links 
           WHERE customer_id = ? AND org_id = ?""",
        (customer_id, org_id)
    ).fetchall()

    # Create Digraph
    dot = graphviz.Digraph(
        comment=f"UBO structure for {customer['full_name']}",
        format="svg",
        graph_attr={
            "rankdir": "BT",  # Bottom-to-top layout (UBOs point up to target entity)
            "bgcolor": "transparent",
            "margin": "0",
            "pad": "0.2",
        },
        node_attr={
            "fontname": "system-ui, -apple-system, sans-serif",
            "fontsize": "11",
            "shape": "box",
            "style": "filled,rounded",
            "penwidth": "1.5",
        },
        edge_attr={
            "fontname": "system-ui, -apple-system, sans-serif",
            "fontsize": "9",
            "penwidth": "1.2",
            "color": "#1E9B8F",  # Teal accent from Grovisor branding
            "arrowsize": "0.8",
        }
    )

    # Customer node details
    cust_color = "#0F2140"  # Navy accent from Grovisor branding
    cust_name = html.escape(customer["full_name"])
    cust_label = (
        f"<<TABLE BORDER='0' CELLBORDER='0' CELLSPACING='4'>\n"
        f"  <TR><TD><B><FONT COLOR='#FFFFFF'>{cust_name}</FONT></B></TD></TR>\n"
        f"  <TR><TD><FONT COLOR='#A0B2C6' POINT-SIZE='9'>{customer['customer_type'].upper()} ENTITY</FONT></TD></TR>\n"
        f"</TABLE>>"
    )
    
    dot.node(
        f"cust_{customer_id}",
        label=cust_label,
        fillcolor=cust_color,
        color=cust_color,
        fontcolor="#FFFFFF",
    )

    if not ubos:
        # If no UBO links, add a placeholder note
        dot.node(
            "no_ubos",
            label="No Beneficial Owners Registered",
            fillcolor="#F8FAFC",
            color="#E2E8F0",
            fontcolor="#64748B",
            style="filled,dashed,rounded",
        )
        dot.edge("no_ubos", f"cust_{customer_id}", style="invis")
        try:
            return dot.pipe().decode("utf-8")
        except Exception:
            log.exception("UBO diagram generation failed for customer %s (no-UBO placeholder)", customer_id)
            return None

    # Add nodes for each UBO
    for i, ubo in enumerate(ubos):
        node_id = f"ubo_{i}"
        
        # Color based on whether they are UBO or other control
        if ubo["is_ubo"]:
            fill_color = "#EBFBFA"
            border_color = "#1E9B8F"
            text_color = "#0F2140"
            role_text = "UBO"
        else:
            fill_color = "#F8FAFC"
            border_color = "#64748B"
            text_color = "#334155"
            role_text = ubo["control_type"].replace("_", " ").title()

        ownership_pct = ubo["ownership_pct"]
        pct_label = f"{ownership_pct}% Ownership" if ownership_pct else "No direct equity"
        
        ubo_name = html.escape(ubo["person_name"])
        ubo_label = (
            f"<<TABLE BORDER='0' CELLBORDER='0' CELLSPACING='2'>\n"
            f"  <TR><TD><B><FONT COLOR='{text_color}'>{ubo_name}</FONT></B></TD></TR>\n"
            f"  <TR><TD><FONT COLOR='#64748B' POINT-SIZE='9'>{role_text} | {pct_label}</FONT></TD></TR>\n"
            f"</TABLE>>"
        )

        dot.node(
            node_id,
            label=ubo_label,
            fillcolor=fill_color,
            color=border_color,
            fontcolor=text_color,
        )

        # Draw edge from UBO to customer
        edge_label = f" {ownership_pct}%" if ownership_pct else f" {role_text}"
        dot.edge(node_id, f"cust_{customer_id}", label=edge_label)

    try:
        # Pipe outputs the SVG contents directly
        return dot.pipe().decode("utf-8")
    except Exception:
        # Fallback if graphviz is not installed locally/fails -- logged rather
        # than swallowed, since a customer.html page missing its diagram with
        # no trace anywhere was previously indistinguishable from "no UBOs".
        log.exception("UBO diagram generation failed for customer %s", customer_id)
        return None
