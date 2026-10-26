"""Provider/storage-independent bounded investigation shared by live and sample runs."""
import time

TOOLS={
 "timeline":("voice_pending","oldest_pending_seconds","throughput","app_reachable"),
 "portal_services":("voice_output_enabled","sms_output_enabled","data_output_enabled","sms_pending","data_pending",
                    "api_process","mediation_process","delivery_process","app_reachable"),
 "host_resources":("cpu_percent","memory_percent","disk_percent"),
 "traffic":("voice_pending","sms_pending","data_pending","throughput","rejected_total")}
REPORT_CONTRACT={"status":"supported_hypothesis or insufficient_evidence","summary":"string",
 "hypotheses":[{"title":"string","explanation":"string","evidence_ids":["known evidence ID"],"confidence":"low/medium/high"}],
 "alternatives":[{"title":"string","explanation":"string","evidence_ids":["known evidence ID"],"confidence":"low/medium/high"}],
 "missing_evidence":["string"],"recommended_checks":["read-only check, never a claim of execution"]}


def validate_report(report,context):
    known={r["evidence_id"] for r in context["evidence"]}
    if report.get("status") not in ("supported_hypothesis","insufficient_evidence"):
        raise ValueError("Invalid report status")
    if not isinstance(report.get("summary"),str) or not 1<=len(report["summary"])<=3000:
        raise ValueError("Invalid report summary")
    for field in ("hypotheses","alternatives"):
        items=report.get(field)
        if not isinstance(items,list) or len(items)>5:raise ValueError("Invalid hypothesis list")
        for item in items:
            if not isinstance(item,dict) or any(not isinstance(item.get(k),str) or not 1<=len(item[k])<=2500 for k in ("title","explanation")):
                raise ValueError("Invalid hypothesis")
            refs=item.get("evidence_ids")
            if not isinstance(refs,list) or any(not isinstance(ref,str) or ref not in known for ref in refs):
                raise ValueError("Unknown evidence citation")
            if not refs:raise ValueError("Hypothesis must cite evidence; put untested ideas in missing_evidence")
            if item.get("confidence") not in ("low","medium","high"):raise ValueError("Invalid confidence")
    if report["status"]=="supported_hypothesis" and not report["hypotheses"]:
        raise ValueError("Supported status requires a cited hypothesis")
    for field in ("missing_evidence","recommended_checks"):
        if not isinstance(report.get(field),list) or len(report[field])>10 or any(not isinstance(v,str) or len(v)>1500 for v in report[field]):
            raise ValueError("Invalid recommendations")
    return report


def review_contract(review):
    if review.get("verdict") not in ("supported","insufficient","revise") or not isinstance(review.get("issues"),list):
        raise ValueError("Invalid evaluator response")
    if any(not isinstance(v,str) or len(v)>1500 for v in review["issues"]):raise ValueError("Invalid evaluator issues")
    return review


def execute(alert,run_id,attempt,generator,evidence_query,ingest,build_context,note,
            now=None,source_name='zetaris',provider_name='meterless_nightshift',requested_model='meterless/auto'):
    context_id=run_id+':attempt:'+str(attempt)
    deadline=time.monotonic()+200
    now=time.time() if now is None else now
    def model(role,payload):
        if len(generator.calls)>=5:raise ValueError("Model-call cap exceeded")
        note("model.started",{"role":role,"requested_model":requested_model})
        try:result=generator.generate(role,payload,deadline)
        except Exception as error:
            note("model.failed",{"role":role,"error_type":type(error).__name__,"automatic_retry":False})
            raise
        if len(generator.calls)>5:raise ValueError("Model-call cap exceeded")
        note("model.completed",generator.calls[-1])
        note("model.output",{"role":role,"output":result})
        return result
    opening=alert["opening_evidence"]
    anchor=float(opening["observed_epoch"])
    host=opening["host_id"]
    start,end=anchor-120,min(now,anchor+120)
    def fetch(tool):
        rows=evidence_query(tool,host,start,end,deadline)
        result=ingest(context_id,host,tool,rows)
        note("world.ingested",{"tool":tool,"rows":len(rows),**result})
    def context(budget=18000):
        result=build_context(context_id,anchor,budget=budget)
        note("world.context_built",{"evidence_count":len(result["evidence"]),"truncated":result["truncated"],"manifest":result["manifest"]})
        return result
    fetch("timeline")
    initial=context(budget=4000)
    if not initial["evidence"]:raise ValueError("No source evidence in incident window")
    objective={"monitor_metric":alert["metric"],"observed_value":opening["value"],"threshold":opening["threshold"],
               "question":"What explains the sustained violation? Distinguish symptoms, service/process state and configuration; consider alternative explanations.",
               "application_flow":"Input portals -> mediation worker -> enabled output portals -> durable outbox. A healthy process can coexist with a disabled portal. A backlog may reflect portal configuration, process failure or resource contention; do not infer those states from queue size alone.",
               "incident_window":{"start_epoch":start,"end_epoch":end},"automatic_remediation":False}
    plan=model("planner",{"contract":{"tools":["portal_services"],"reason":"Explain which evidence gap the selected tools address"},
         "instruction":"Choose zero, one or two distinct allowed tool names based on this incident. The contract is a shape example, not a prescribed choice.",
         "allowed_tools":{k:list(v) for k,v in TOOLS.items() if k!="timeline"},"objective":objective,"context":initial})
    selected=plan.get("tools")
    if not isinstance(selected,list) or len(selected)>2 or len(set(selected))!=len(selected) or any(t not in TOOLS or t=="timeline" for t in selected):
        raise ValueError("Planner chose invalid tools")
    note("planner.selected_tools",{"tools":selected,"reason":str(plan.get("reason",""))[:1000]})
    requested_tools=list(selected)
    # A symptom-only query cannot support an explanation. This explicit evidence
    # policy adds the relevant state source; the model still chooses supplemental tools.
    required="portal_services" if alert["metric"]=="voice_pending" else "host_resources"
    if required not in selected:
        selected=selected[:1]+[required]
        note("policy.required_evidence_tool",{"tool":required,"model_requested":requested_tools,
              "executed_tools":selected,"reason":"Verify configuration/process or host state rather than only restating a symptom"})
    for tool in selected:fetch(tool)
    grounded=context()
    report=model("investigator",{"contract":REPORT_CONTRACT,"objective":objective,"context":grounded})
    guard=[]
    try:validate_report(report,grounded)
    except ValueError as error:guard=[str(error)]
    critique_payload={"contract":{"verdict":"supported/insufficient/revise","issues":["specific unsupported claims, contradictions, uncertainty or citation problems"]},
        "instruction":"Independently inspect every factual claim against cited evidence. A citation existing is not proof it supports the claim. Never mark an unobserved causal claim as established. Demand uncertainty if evidence is missing.",
        "objective":objective,"context":grounded,"report":report,"structural_issues":guard}
    review=review_contract(model("evaluator",critique_payload))
    if guard or review["verdict"]=="revise":
        note("report.revision_requested",{"issues":guard+review["issues"]})
        report=model("investigator_revision",{"contract":REPORT_CONTRACT,"objective":objective,"context":grounded,
                     "previous_report":report,"required_corrections":guard+review["issues"]})
        validate_report(report,grounded)
        critique_payload.update(report=report,structural_issues=[])
        review=review_contract(model("final_evaluator",critique_payload))
    else:validate_report(report,grounded)
    report["review"]=review
    report["evidence"]=grounded["evidence"]
    report["scope"]={"historical_incident_window":True,"start_epoch":start,"end_epoch":end,"remediation_executed":False}
    manifest={**grounded["manifest"],"world_context_key":context_id,"model_calls":generator.calls,
              "planner_requested_tools":requested_tools,"required_evidence_tool":required,"evidence_tools":["timeline"]+selected,
              "max_model_calls":5,"max_tool_queries":3,"deadline_seconds":200,"source":source_name,"provider":provider_name}
    status="needs_review" if review["verdict"]=="revise" else "completed"
    if review["verdict"]=="insufficient":report["status"]="insufficient_evidence"
    return {"status":status,"report":report,"manifest":manifest}
