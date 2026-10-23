// Exercises the real same-origin HTTP path without storing passwords or cookies.
import { randomBytes } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
const origin = process.env.SMOKE_ORIGIN || "http://localhost:8080";
const jar = new Map();
async function request(path, options = {}) {
  const response = await fetch(origin + path, { ...options, headers: { Cookie: [...jar].map(([k,v])=>`${k}=${v}`).join("; "), ...options.headers } });
  for (const cookie of response.headers.getSetCookie()) { const [pair] = cookie.split(";"); const separator=pair.indexOf("="); jar.set(pair.slice(0,separator),pair.slice(separator+1)); }
  return response;
}
const csrf = await (await request("/api/v1/auth/csrf")).json();
const email = `smoke-${randomBytes(8).toString("hex")}@example.com`;
const register = await request("/api/v1/auth/register", { method:"POST",headers:{"Content-Type":"application/json",Origin:origin,"X-CSRF-Token":csrf.csrf_token},body:JSON.stringify({email,password:randomBytes(24).toString("hex"),name:"Temporary smoke check",workspace_name:"Temporary smoke check"}) });
if (register.status!==201) throw new Error(`Registration failed: ${register.status}`);
const session=await register.json(), workspace=session.workspaces[0].id;
await mkdir(".local",{recursive:true});
await writeFile(".local/smoke-resource.json",JSON.stringify({email,user_id:session.user.id,workspace_id:workspace}));
const mutationHeaders={"Content-Type":"application/json",Origin:origin,"X-CSRF-Token":session.csrf_token};
const agentResponse=await request(`/api/v1/workspaces/${workspace}/agents`,{method:"POST",headers:mutationHeaders,body:JSON.stringify({name:"Smoke test agent"})});
if(agentResponse.status!==201)throw new Error("Agent save failed");
const agent=await agentResponse.json();
const workflowResponse=await request(`/api/v1/workspaces/${workspace}/workflows`,{method:"POST",headers:mutationHeaders,body:JSON.stringify({name:"Smoke test workflow"})});
if(workflowResponse.status!==201)throw new Error("Workflow save failed");
const workflow=await workflowResponse.json();
for(const path of ["/","/login","/register",`/w/${workspace}/overview`,`/w/${workspace}/agents`,`/w/${workspace}/agents/${agent.id}`,`/w/${workspace}/agents/${agent.id}?tab=versions`,`/w/${workspace}/agents/${agent.id}/test`,`/w/${workspace}/integrations`,`/w/${workspace}/workflows`,`/w/${workspace}/workflows/${workflow.id}/edit`,`/w/${workspace}/settings`]){
 const response=await request(path);const body=await response.text();
 if(response.status!==200||!body.includes("FlowForge")||(path.startsWith("/w/")&&response.redirected))throw new Error(`Page failed: ${path} (${response.status})`);
 console.log(`OK ${path.replaceAll(workspace,"[workspace]").replaceAll(agent.id,"[agent]").replaceAll(workflow.id,"[workflow]")}`);
}
console.log("HTTP smoke check passed. Temporary-resource identifiers saved for cleanup; credentials were not saved.");
