"""Portable action patterns. Workspace connections are deliberately unbound."""


def node(identity, kind, label, x, y=180, config=None):
    return {"id": identity, "type": kind, "label": label, "position": {"x": x, "y": y}, "config": config or {}}


def edge(source, target, port="out", mappings=None):
    return {"id": f"{source}-{target}", "source": source, "target": target, "source_port": port, "mappings": mappings or []}


def action_starters():
    return {
        "webhook-api-action": {
            "key": "webhook-api-action", "kind": "workflow", "name": "Webhook to API action", "category": "Service actions", "template_version": 1,
            "description": "Receive an event, shape its payload and send it to an approved API. Connect your destination before publishing.",
            "setup_steps": ["In Tool Registry, approve a fixed POST endpoint and its JSON contract.", "Select that API tool in Send event. Adjust the Build payload fields to its contract.", "Publish and test a run, then create a webhook in Triggers & schedules. Keep its key on your app server."],
            "sample_input": {"event_id": "evt-001", "message": "A customer requested a demo."},
            "graph": {"schema_version": 1,
                      "nodes": [node("input", "webhook_trigger", "Incoming event", 60), node("payload", "transform", "Build payload", 360, config={"fields": {"event_id": {"kind": "input", "pointer": "/event_id"}, "message": {"kind": "input", "pointer": "/message"}}}), node("send", "http_tool", "Send event", 660), node("result", "result", "Return receipt", 960)],
                      "edges": [edge("input", "payload"), edge("payload", "send"), edge("send", "result")],
                      "input_schema": {"type": "object", "properties": {"event_id": {"type": "string"}, "message": {"type": "string"}}, "required": ["event_id", "message"], "additionalProperties": False}, "output_schema": {"type": "object"}},
        },
        "scheduled-api-digest": {
            "key": "scheduled-api-digest", "kind": "workflow", "name": "Scheduled API digest", "category": "Service actions", "template_version": 1,
            "description": "Fetch records, filter open items and return a digest on a persistent interval.",
            "setup_steps": ["Approve a read-only GET API tool whose JSON response has an items array.", "Select it in Fetch records; configure query input for your endpoint.", "Adjust the filter and publish. Set interval and saved input in Triggers & schedules."],
            "sample_input": {},
            "graph": {"schema_version": 1,
                      "nodes": [node("input", "schedule_trigger", "Scheduled input", 60), node("fetch", "http_tool", "Fetch records", 360), node("filter", "list_filter", "Keep open items", 660, config={"source": "/body/items", "item_pointer": "/status", "operator": "eq", "value": "open"}), node("result", "result", "Open items", 960)],
                      "edges": [edge("input", "fetch"), edge("fetch", "filter"), edge("filter", "result")],
                      "input_schema": {"type": "object"}, "output_schema": {"type": "object"}},
        },
        "agent-priority-action": {
            "key": "agent-priority-action", "kind": "workflow", "name": "AI priority routing with action", "category": "AI automation", "template_version": 1,
            "description": "Classify a ticket, send urgent cases to an approved API and retain the normal path without sending an action.",
            "setup_steps": ["Create the Support ticket triage agent template, choose a model and publish it. Select its version in Classify ticket.", "Approve an API tool accepting priority and reason. Select it in Escalate urgent.", "Validate, publish and test both urgent and normal inputs. Review automated routing policy before enabling a webhook."],
            "sample_input": {"ticket": "Our payment service is down and customers cannot check out."},
            "graph": {"schema_version": 1,
                      "nodes": [node("input", "manual_input", "Support ticket", 60, 250), node("classify", "agent", "Classify ticket", 340, 250), node("decision", "condition", "Urgent?", 620, 250, {"left": {"kind": "input", "pointer": "/priority"}, "operator": "eq", "right": {"kind": "literal", "value": "urgent"}}), node("escalate", "http_tool", "Escalate urgent", 900, 100), node("normal", "transform", "Standard queue", 900, 400, {"fields": {"queue": {"kind": "literal", "value": "standard"}, "reason": {"kind": "input", "pointer": "/reason"}}}), node("result", "result", "Routing result", 1180, 250)],
                      "edges": [edge("input", "classify"), edge("classify", "decision"), edge("decision", "escalate", "true"), edge("decision", "normal", "false"), edge("escalate", "result"), edge("normal", "result")],
                      "input_schema": {"type": "object", "properties": {"ticket": {"type": "string"}}, "required": ["ticket"], "additionalProperties": False}, "output_schema": {"type": "object"}},
        },
    }
