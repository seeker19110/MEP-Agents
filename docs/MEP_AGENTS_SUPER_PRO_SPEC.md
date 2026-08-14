# MEP-Agents Super Pro V2 — Master Product & Technical Specification

> **Status:** Proposed / Architecture Baseline
>
> **Repository:** `seeker19110/MEP-Agents`
>
> **Purpose:** Chuyển MEP-Agents từ một multi-agent engineering prototype thành nền tảng AI Engineering Platform có khả năng hiểu công trình, CAD/BIM, tính toán kỹ thuật deterministic, kiểm tra tiêu chuẩn, phối hợp MEPF, bóc khối lượng, dự toán, tối ưu thiết kế và tạo deliverables có truy xuất nguồn gốc.

---

## 1. Tầm nhìn sản phẩm

MEP-Agents Super Pro là một **Engineering Digital Twin + AI Engineering Operating System**.

Sản phẩm không được định vị là chatbot hỏi đáp về MEP. Hệ thống phải có khả năng:

```text
Input
  ├── DWG / DXF
  ├── PDF
  ├── IFC / BIM
  ├── Excel / BOQ
  ├── Specifications
  ├── Standards
  └── Project requirements
        ↓
Project Understanding
        ↓
Digital Twin + Engineering Knowledge Graph
        ↓
Deterministic Engineering Engines
        ↓
AI Agents / Planning / Reasoning
        ↓
Validation + Standards + Coordination
        ↓
Human Approval
        ↓
CAD / BIM / BOQ / Estimate / Reports
```

### 1.1 Mục tiêu dài hạn

Hệ thống phải tiến tới việc người dùng có thể yêu cầu:

> “Phân tích toàn bộ tầng 5, phát hiện lỗi MEP, đề xuất 3 phương án xử lý, kiểm tra tiêu chuẩn, tính lại tải, tối ưu chi phí, cập nhật bản vẽ và xuất báo cáo thay đổi.”

và hệ thống thực hiện theo workflow có kiểm soát, không để LLM tự ý thực hiện các phép tính kỹ thuật hoặc thay đổi quan trọng mà không có validation.

---

# 2. Nguyên tắc kiến trúc bắt buộc

## 2.1 Deterministic Engineering First

LLM **không phải calculation engine**.

LLM chỉ:

- hiểu yêu cầu;
- lập kế hoạch;
- chọn tool;
- truyền input có cấu trúc;
- diễn giải kết quả;
- đề xuất phương án;
- tổng hợp báo cáo.

Các phép tính phải nằm trong deterministic engines.

Ví dụ:

```text
User
 ↓
Electrical Agent
 ↓
Tool Router
 ↓
Cable Calculation Engine
 ↓
Current / Voltage Drop / Short Circuit / Derating
 ↓
Validation
 ↓
Agent explanation
```

Không cho phép workflow:

```text
LLM → tự suy đoán tiết diện cáp → xuất bản vẽ
```

---

## 2.2 Evidence First

Mọi kết quả kỹ thuật quan trọng phải truy xuất được:

```text
Result
 ├── Inputs
 ├── Formula / Rule
 ├── Calculation engine
 ├── Standard
 ├── Standard version
 ├── Source document
 ├── Source entity / geometry
 ├── Model / agent
 ├── Timestamp
 └── Validation status
```

Người dùng phải có thể hỏi:

> “Tại sao hệ thống chọn phương án này?”

và xem được evidence chain.

---

## 2.3 Human-in-the-loop

Các thao tác ảnh hưởng tới thiết kế phát hành, an toàn, PCCC, điện bảo vệ, kết cấu interface hoặc hồ sơ chính thức phải có human approval.

Mức tự động hóa:

| Confidence / Risk | Hành động |
|---|---|
| High confidence + low risk | Có thể auto |
| High confidence + medium risk | Suggest + approval tùy policy |
| Medium confidence | Human review |
| Low confidence | Không thực hiện |
| Safety-critical | Human approval bắt buộc |

---

## 2.4 Model Agnostic

Không khóa business logic vào một LLM.

Model Router phải có khả năng chọn model theo:

- task;
- modality;
- complexity;
- latency;
- cost;
- confidence;
- availability;
- project policy.

Có fallback giữa nhiều provider và khả năng dùng local model khi phù hợp.

---

## 2.5 Domain Logic độc lập Agent

Không nhúng engineering rules vào prompt agent.

Kiến trúc phải là:

```text
Agent
 ↓
Domain Service / Tool
 ↓
Deterministic Engine
```

để calculation engine có thể được gọi từ:

- AI Agent;
- REST API;
- batch job;
- test suite;
- CLI;
- future desktop plugin.

---

# 3. Product Scope

## 3.1 Core modules

1. Project Workspace
2. Document Management
3. CAD Intelligence
4. BIM Intelligence
5. Digital Twin
6. Engineering Knowledge Graph
7. Mechanical / HVAC
8. Electrical
9. Plumbing
10. Fire Protection
11. Engineering Calculation Engine
12. Standards Engine
13. Rule Engine
14. Coordination / Clash Engine
15. Quantity Takeoff
16. BOQ
17. Cost / Estimate
18. Design Alternatives
19. Optimization Engine
20. Revision / Change Impact
21. AI Orchestration
22. Model Router
23. Review Board
24. Evidence / Audit
25. Reporting / Export
26. Collaboration
27. Multi-tenancy / RBAC
28. Billing / Usage
29. Observability
30. Evaluation / Benchmarking

---

# 4. Target architecture

```text
                           ┌──────────────────────┐
                           │      WEB APP         │
                           │ Next.js / React / TS │
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │      API GATEWAY     │
                           │ Auth / RBAC / Rate   │
                           └──────────┬───────────┘
                                      │
             ┌────────────────────────┼────────────────────────┐
             ▼                        ▼                        ▼
       Project API              AI API                  File API
             │                        │                        │
             └────────────────────────┼────────────────────────┘
                                      ▼
                           ┌──────────────────────┐
                           │  AI ORCHESTRATOR     │
                           │ Planner / Router     │
                           └──────────┬───────────┘
                                      │
             ┌────────────────────────┼────────────────────────┐
             ▼                        ▼                        ▼
        Domain Agents            Tool Router             Review Board
             │                        │                        │
     ┌───────┼────────┐       ┌───────┼────────┐               │
     ▼       ▼        ▼       ▼       ▼        ▼               ▼
   HVAC   Electrical Plumbing CAD    BIM       QS          QA / Safety
     │       │        │       │       │        │               │
     └───────┴────────┴───────┴───────┴────────┴───────────────┘
                                      │
                                      ▼
                       ┌──────────────────────────┐
                       │ ENGINEERING CORE         │
                       │                          │
                       │ Calculation Engine       │
                       │ Geometry Engine           │
                       │ Standards Engine          │
                       │ Rule Engine               │
                       │ Spatial Engine            │
                       │ Quantity Engine           │
                       │ Cost Engine               │
                       └────────────┬─────────────┘
                                    │
                                    ▼
                     ┌────────────────────────────┐
                     │ DIGITAL TWIN + GRAPH       │
                     │                            │
                     │ Project / Building / Floor │
                     │ Space / System / Equipment │
                     │ Network / Drawing / IFC    │
                     └────────────┬───────────────┘
                                  │
               ┌──────────────────┼──────────────────┐
               ▼                  ▼                  ▼
          PostgreSQL            Redis/SQS           Object Storage
          Metadata              Queue               S3/MinIO
               │                  │                  │
               └──────────────────┼──────────────────┘
                                  ▼
                            WORKER POOL
                    CAD / BIM / OCR / AI / QS / PDF
```

---

# 5. Repository target structure

```text
MEP-Agents/
├── apps/
│   ├── web/                    # Next.js production UI
│   ├── api/                    # FastAPI API layer
│   └── admin/                  # Internal admin console
│
├── src/
│   ├── agents/                 # Agent orchestration only
│   ├── domain/                 # Domain entities and value objects
│   ├── services/               # Application services
│   ├── engines/                # Deterministic engines
│   │   ├── engineering/
│   │   ├── geometry/
│   │   ├── cad/
│   │   ├── bim/
│   │   ├── standards/
│   │   ├── rules/
│   │   ├── quantity/
│   │   └── cost/
│   ├── graph/                  # Digital twin / engineering graph
│   ├── orchestration/          # Workflow / queue / state machine
│   ├── llm/                    # Model adapters + routing
│   ├── storage/                # DB / object storage
│   ├── security/
│   ├── observability/
│   └── reporting/
│
├── data/
│   ├── standards/
│   ├── catalogs/
│   ├── templates/
│   └── benchmarks/
│
├── autocad/
│   └── ...
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── engineering/
│   ├── cad/
│   ├── bim/
│   ├── agents/
│   ├── security/
│   ├── regression/
│   └── evaluation/
│
├── migrations/
├── infrastructure/
│   ├── docker/
│   ├── terraform/
│   └── kubernetes/
│
└── docs/
    ├── architecture/
    ├── api/
    ├── engineering/
    └── operations/
```

---

# 6. Digital Twin

Digital Twin là trung tâm dữ liệu của toàn hệ thống.

## 6.1 Hierarchy

```text
Organization
└── Project
    └── Building
        └── Level
            └── Zone
                └── Space
                    └── System
                        └── Equipment / Component
                            └── Connection / Network
```

## 6.2 Stable identity

Mọi object phải có stable ID, ví dụ:

```json
{
  "id": "equipment:FCU-001",
  "type": "FCU",
  "project_id": "project-001",
  "building_id": "building-A",
  "level_id": "L02",
  "space_id": "ROOM-203",
  "source_refs": [
    {
      "file_id": "drawing-001",
      "entity_id": "cad-entity-123",
      "revision_id": "rev-03"
    }
  ]
}
```

## 6.3 Required relations

Hệ thống phải hỗ trợ quan hệ như:

- `contains`
- `located_in`
- `serves`
- `connects_to`
- `powered_by`
- `supplied_by`
- `drains_to`
- `controls`
- `depends_on`
- `intersects`
- `near`
- `supports`
- `replaces`
- `derived_from`

---

# 7. Engineering Knowledge Graph

Graph phải hỗ trợ truy vấn quan hệ và impact analysis.

Ví dụ:

```text
FCU-03
 ├── serves → ROOM-203
 ├── connected_to → DUCT-021
 ├── powered_by → DB-02
 ├── controlled_by → BMS-07
 └── condensate_to → DRAIN-11
```

Khi FCU-03 thay đổi, graph phải cho phép tìm tất cả object bị ảnh hưởng.

---

# 8. CAD Intelligence Engine

## 8.1 Parsing pipeline

```text
DWG/DXF
 ↓
Validation
 ↓
Parser
 ↓
Entity normalization
 ↓
Layer/block/text extraction
 ↓
Geometry extraction
 ↓
Semantic classification
 ↓
Spatial index
 ↓
Engineering graph
```

## 8.2 Semantic objects

Phải chuyển entity CAD thành object có nghĩa kỹ thuật:

```text
BLOCK → FCU / Valve / Panel / Pump / Sprinkler
POLYLINE → Pipe / Duct / Cable Tray
TEXT → Tag / Size / Specification
LINE → Segment / Boundary / Connection
```

## 8.3 CAD operations

MVP+ phải hỗ trợ:

- layer standardization;
- block normalization;
- purge;
- overkill;
- duplicate detection;
- annotation validation;
- dimension validation;
- connectivity checking;
- revision diff;
- semantic replacement;
- batch modification;
- safe rollback;
- source-to-output traceability.

## 8.4 Safe CAD mutation

Không sửa file trực tiếp không kiểm soát.

```text
Original
 ↓
Snapshot
 ↓
Proposed mutation
 ↓
Validation
 ↓
Preview / Diff
 ↓
Human approval
 ↓
Apply
 ↓
New revision
```

---

# 9. BIM Intelligence

## 9.1 IFC pipeline

```text
IFC
 ↓
Parse
 ↓
Normalize
 ↓
Property extraction
 ↓
Geometry extraction
 ↓
Spatial indexing
 ↓
Graph mapping
 ↓
Coordination
```

## 9.2 Clash intelligence

Không chỉ detect intersection.

Phải phân loại:

- Hard clash;
- Soft clash;
- Clearance violation;
- Access violation;
- Maintenance violation;
- Code violation;
- Constructability issue;
- Sequence issue.

Mỗi clash có severity:

```text
Critical / High / Medium / Low / Informational
```

---

# 10. Engineering Calculation Engine

Mỗi calculation phải có schema thống nhất.

```json
{
  "calculation_id": "calc-001",
  "discipline": "electrical",
  "calculation_type": "voltage_drop",
  "inputs": {},
  "assumptions": [],
  "formula_version": "v1",
  "engine_version": "2026.1",
  "results": {},
  "warnings": [],
  "standards": [],
  "evidence": [],
  "validation": {
    "status": "passed"
  }
}
```

## 10.1 Discipline engines

### Mechanical / HVAC

- cooling load;
- heating load;
- airflow;
- duct sizing;
- pipe sizing;
- pressure drop;
- pump selection;
- fan selection;
- equipment selection;
- noise checks;
- ventilation.

### Electrical

- load schedule;
- demand factor;
- cable sizing;
- voltage drop;
- short circuit;
- breaker selection;
- panel sizing;
- transformer loading;
- power factor;
- earthing;
- cable tray loading.

### Plumbing

- water demand;
- pipe sizing;
- pressure loss;
- pump sizing;
- tank sizing;
- drainage sizing;
- fixture unit calculations.

### Fire

- sprinkler demand;
- fire pump;
- tank sizing;
- pipe sizing;
- hydraulic calculation;
- fire alarm quantity;
- extinguisher coverage.

---

# 11. Standards Engine

RAG không được là nguồn duy nhất để quyết định compliance.

## 11.1 Pipeline

```text
Source documents
 ↓
Versioned ingestion
 ↓
Section extraction
 ↓
Rule extraction
 ↓
Structured rule store
 ↓
Semantic retrieval
 ↓
Rule engine
 ↓
Evidence
```

## 11.2 Standard record

```json
{
  "standard_id": "TCVN-XXXX",
  "version": "2026",
  "jurisdiction": "VN",
  "discipline": "electrical",
  "section": "X.Y",
  "rule_type": "constraint",
  "rule": "...",
  "source": "...",
  "effective_date": "..."
}
```

Không được trộn các phiên bản tiêu chuẩn mà không ghi rõ version.

---

# 12. Rule Engine

Rule engine dùng cho các constraint có thể biểu diễn deterministic.

Ví dụ:

```text
IF pipe_diameter >= 100
AND zone = fire_zone_A
THEN clearance >= 600mm
```

AI có thể trích xuất facts nhưng rule engine quyết định pass/fail.

---

# 13. Quantity Takeoff / BOQ / Cost

## 13.1 Pipeline

```text
Digital Twin
 ↓
Object extraction
 ↓
Measurement
 ↓
Quantity normalization
 ↓
Specification mapping
 ↓
Material mapping
 ↓
Labor / Equipment
 ↓
Waste / coefficients
 ↓
Unit price
 ↓
BOQ
 ↓
Estimate
```

## 13.2 Traceability

Mỗi BOQ line phải biết nó đến từ đâu:

```text
BOQ item
 ↓
Quantity
 ↓
Objects
 ↓
Drawing entities / BIM elements
 ↓
Revision
```

## 13.3 Cost alternatives

Hệ thống phải hỗ trợ so sánh:

- material;
- equipment;
- system architecture;
- supplier/catalog;
- installation method;
- CAPEX;
- OPEX;
- maintenance cost.

---

# 14. Design Alternatives

Mọi bài toán thiết kế phức tạp nên có khả năng tạo nhiều phương án.

```text
Requirements
 ↓
Design Planner
 ↓
Option A / B / C
 ↓
Calculation
 ↓
Standards
 ↓
Coordination
 ↓
Cost
 ↓
Energy / performance
 ↓
Score
```

Ví dụ score:

```text
Technical compliance: 30%
CAPEX: 25%
OPEX: 20%
Maintainability: 10%
Coordination: 10%
Availability: 5%
```

Trọng số phải configurable theo project.

---

# 15. Optimization Engine

Optimization phải dựa trên objective + constraints.

```text
Objective
 ├── minimize cost
 ├── minimize energy
 ├── minimize duct length
 ├── minimize shaft size
 └── maximize maintainability

Constraints
 ├── standards
 ├── geometry
 ├── capacity
 ├── safety
 └── project requirements
```

Không được cho phép optimizer phá vỡ hard constraints.

---

# 16. Revision & Change Impact

Mỗi project có revision graph:

```text
REV-01
  ↓
REV-02
  ↓
REV-03
```

Mỗi revision phải biết:

- changed objects;
- added objects;
- removed objects;
- changed calculations;
- changed BOQ;
- changed cost;
- changed compliance;
- changed clashes.

## 16.1 Change impact example

Nếu `FCU-03` đổi công suất:

```text
FCU-03
 ├── airflow
 ├── duct
 ├── electrical load
 ├── breaker
 ├── cable
 ├── panel
 ├── BMS
 ├── BOQ
 └── estimate
```

Hệ thống phải tự tạo impact report.

---

# 17. AI Orchestration

## 17.1 Agent responsibilities

Agent chỉ chịu trách nhiệm:

- planning;
- reasoning;
- tool selection;
- task decomposition;
- interpretation;
- communication.

## 17.2 Agent hierarchy

```text
Project Manager Agent
        ↓
Engineering Planner
        ↓
Domain Agents
 ├── Mechanical
 ├── Electrical
 ├── Plumbing
 ├── Fire
 ├── CAD
 ├── BIM
 └── QS
        ↓
Review Board
```

## 17.3 Review Board

```text
Engineering Reviewer
Standards Reviewer
Coordination Reviewer
Safety Reviewer
Cost Reviewer
Final Reviewer
```

Reviewer phải trả về structured decision:

```json
{
  "decision": "approve | revise | reject",
  "severity": "critical | high | medium | low",
  "issues": [],
  "required_actions": [],
  "evidence": []
}
```

---

# 18. Model Router

Model selection phải theo task.

```text
Task
 ↓
Classifier
 ↓
Complexity
 ↓
Risk
 ↓
Budget
 ↓
Model Router
```

Routing dimensions:

- fast/cheap;
- reasoning;
- vision;
- long context;
- coding;
- multilingual;
- structured output.

## 18.1 Escalation

```text
Cheap model
 ↓
confidence high → accept
confidence low → stronger model
 ↓
reviewer
```

## 18.2 Fallback

```text
Provider A
 ↓ failure
Provider B
 ↓ failure
Provider C
 ↓ failure
Local model
```

---

# 19. Evidence & Audit System

Mỗi action phải có audit event.

```json
{
  "event_id": "evt-001",
  "project_id": "project-001",
  "actor": "user|agent|system",
  "action": "modify_drawing",
  "input_refs": [],
  "output_refs": [],
  "model": "...",
  "tool": "...",
  "timestamp": "...",
  "approval": {
    "required": true,
    "approved_by": "..."
  }
}
```

Audit log không được chỉnh sửa bởi user thông thường.

---

# 20. Project Workspace

Production UI phải là workspace, không phải chatbot-centric.

```text
Project
├── Overview
├── Documents
├── Drawings
├── BIM
├── Mechanical
├── Electrical
├── Plumbing
├── Fire
├── Coordination
├── Quantities
├── BOQ
├── Estimate
├── Issues
├── Revisions
├── Reports
└── AI Assistant
```

## 20.1 Ask the Building

Người dùng có thể hỏi:

- Có bao nhiêu FCU?
- FCU nào chưa có nguồn?
- Tổng tải điện tầng 3?
- Có clash nghiêm trọng nào?
- Tại sao BOQ revision 03 tăng?
- Nếu di chuyển AHU-02 thì ảnh hưởng gì?
- Có vi phạm clearance nào?

Câu trả lời phải dựa trên Digital Twin + graph + engines + evidence, không chỉ RAG.

---

# 21. API architecture

API phải versioned:

```text
/api/v1/projects
/api/v1/documents
/api/v1/drawings
/api/v1/bim
/api/v1/engineering
/api/v1/calculations
/api/v1/standards
/api/v1/coordination
/api/v1/quantities
/api/v1/boq
/api/v1/estimates
/api/v1/revisions
/api/v1/agents
/api/v1/jobs
```

Long-running operations trả job ID:

```json
{
  "job_id": "job-001",
  "status": "queued"
}
```

Không giữ HTTP request mở cho các job CAD/BIM/AI dài.

---

# 22. Event-driven processing

Các event chuẩn:

```text
PROJECT_CREATED
DOCUMENT_UPLOADED
DRAWING_PARSED
BIM_IMPORTED
OBJECTS_EXTRACTED
GRAPH_UPDATED
CALCULATION_REQUESTED
CALCULATION_COMPLETED
CLASH_DETECTED
QUANTITY_UPDATED
BOQ_UPDATED
ESTIMATE_UPDATED
REVISION_CREATED
APPROVAL_REQUESTED
APPROVED
REJECTED
EXPORT_REQUESTED
EXPORT_COMPLETED
```

Worker queues:

```text
cad-worker
bim-worker
ocr-worker
ai-worker
engineering-worker
quantity-worker
cost-worker
report-worker
```

---

# 23. Data architecture

## 23.1 PostgreSQL

Lưu:

- organizations;
- users;
- projects;
- buildings;
- spaces;
- systems;
- equipment;
- drawings metadata;
- BIM metadata;
- jobs;
- calculations;
- quantities;
- BOQ;
- estimates;
- revisions;
- issues;
- approvals;
- audit events.

## 23.2 Object storage

Lưu:

- DWG;
- DXF;
- IFC;
- PDF;
- Excel;
- generated files;
- reports;
- snapshots.

Không lưu binary lớn trực tiếp trong PostgreSQL.

## 23.3 Redis / Queue

Dùng cho:

- job queue;
- cache;
- rate limit;
- short-lived state;
- distributed locks.

---

# 24. Multi-tenancy

Hierarchy:

```text
Organization
 ├── Members
 ├── Teams
 ├── Projects
 ├── API Keys
 └── Billing
```

Tenant isolation phải được enforce ở application + database layer.

Không được dựa chỉ vào UI để bảo mật.

---

# 25. RBAC

Roles tối thiểu:

- Owner
- Admin
- Project Manager
- MEP Engineer
- QS
- Reviewer
- Client
- Viewer

Permission phải kiểm soát tới project/object/action khi cần.

---

# 26. Security

Bắt buộc:

- authentication;
- authorization;
- tenant isolation;
- signed upload URLs;
- file type validation;
- malware scanning;
- path traversal protection;
- secrets management;
- encryption at rest;
- TLS;
- rate limiting;
- audit logs;
- secure worker sandbox;
- dependency scanning;
- prompt injection defense;
- tool authorization.

## 26.1 Tool authorization

Agent không được gọi mọi tool.

Ví dụ:

```text
Read drawing → allowed
Calculate → allowed
Modify drawing → approval required
Delete revision → admin only
Publish deliverable → authorized reviewer only
```

---

# 27. Prompt / Agent Security

Untrusted document content không được trở thành system instruction.

Pipeline:

```text
Document
 ↓
Extracted content
 ↓
Marked as untrusted data
 ↓
Agent context
```

Phải chống:

- prompt injection trong PDF;
- malicious text trong CAD metadata;
- tool abuse;
- data exfiltration;
- cross-tenant retrieval.

---

# 28. Testing strategy

## 28.1 Unit tests

Test từng calculation và domain rule.

## 28.2 Integration tests

Test:

```text
API → DB → Queue → Worker → Result
```

## 28.3 CAD regression

Golden DWG/DXF fixtures.

## 28.4 BIM regression

Golden IFC fixtures.

## 28.5 Engineering regression

Golden calculation cases với expected results.

## 28.6 Security tests

- auth bypass;
- tenant isolation;
- path traversal;
- malicious files;
- prompt injection;
- SSRF/tool abuse.

---

# 29. AI Evaluation

Tạo benchmark dataset cố định.

```text
evaluation/
├── mechanical/
├── electrical/
├── plumbing/
├── fire/
├── cad/
├── bim/
├── qs/
└── general/
```

Metrics:

- task success;
- calculation correctness;
- tool selection accuracy;
- hallucination rate;
- evidence completeness;
- standard citation correctness;
- latency;
- token usage;
- cost;
- reviewer acceptance rate.

Mọi thay đổi model/prompt/agent phải chạy evaluation trước khi production.

---

# 30. Observability

Mỗi request phải có trace ID.

```text
Request
 ├── planner
 ├── model call
 ├── tool call
 ├── worker
 ├── calculation
 ├── reviewer
 └── final response
```

Metrics:

- p50/p95/p99 latency;
- queue depth;
- worker failures;
- LLM cost;
- tokens;
- model error rate;
- calculation failures;
- approval rate;
- retry rate.

---

# 31. Performance targets

Initial production targets:

| Metric | Target |
|---|---:|
| Simple API p95 | < 500 ms |
| Metadata query p95 | < 1 s |
| Chat first token | < 3 s |
| Job submission | < 500 ms |
| Standard retrieval | < 1 s |
| Calculation tool | < 2 s for normal case |
| UI interactive action | < 300 ms perceived |
| Worker retry | automatic |
| Long job | asynchronous |

CAD/BIM processing time phải phụ thuộc kích thước file và được báo progress.

---

# 32. Reliability

Yêu cầu:

- idempotent jobs;
- retry with backoff;
- dead-letter queue;
- checkpoint;
- resumable processing;
- transactional state changes;
- immutable revisions;
- backup;
- disaster recovery.

Job phải có trạng thái:

```text
QUEUED
RUNNING
WAITING_REVIEW
SUCCEEDED
FAILED
CANCELLED
```

---

# 33. Reporting

Hệ thống phải tạo được:

- Engineering calculation report;
- Design report;
- Clash report;
- Compliance report;
- BOQ;
- Estimate;
- Revision report;
- Change impact report;
- AI decision report;
- Audit report.

Mọi report phải có version và source references.

---

# 34. Export

Mục tiêu:

- PDF;
- Excel/XLSX;
- CSV;
- DWG/DXF;
- IFC;
- JSON;
- project package.

Export phải được tạo từ canonical project state, không từ nội dung chat.

---

# 35. Billing / Usage

Usage phải theo dõi:

- LLM tokens;
- model calls;
- CAD processing;
- BIM processing;
- storage;
- worker compute;
- exports.

Quota examples:

```text
Free
Pro
Business
Enterprise
```

Billing policy không được nằm trong agent prompt; phải nằm trong usage service.

---

# 36. Development workflow

```text
Requirement
 ↓
Architecture Decision
 ↓
GitHub Issue
 ↓
Implementation Plan
 ↓
Branch
 ↓
Code
 ↓
Unit Tests
 ↓
Integration Tests
 ↓
AI Evaluation
 ↓
PR
 ↓
Review
 ↓
CI
 ↓
Staging
 ↓
Acceptance
 ↓
Production
```

Không phát triển trực tiếp trên production branch.

---

# 37. Definition of Done

Một feature chỉ được coi là hoàn thành khi:

- [ ] requirements rõ;
- [ ] domain model rõ;
- [ ] API contract rõ;
- [ ] implementation hoàn thành;
- [ ] unit tests;
- [ ] integration tests nếu cần;
- [ ] security review nếu có file/tool;
- [ ] observability;
- [ ] error handling;
- [ ] documentation;
- [ ] migration nếu có DB;
- [ ] evaluation nếu có AI;
- [ ] backward compatibility được xem xét;
- [ ] CI pass;
- [ ] staging verified.

---

# 38. Roadmap triển khai

## Phase 0 — Baseline & Safety

Ưu tiên:

1. Freeze current baseline.
2. Tạo architecture decision records.
3. Chuẩn hóa config.
4. Xóa secrets/artifacts khỏi repo nếu có.
5. Thiết lập test baseline.
6. Thiết lập lint/type checking.
7. Thiết lập observability baseline.

## Phase 1 — Core Refactor

1. Domain models.
2. Typed contracts.
3. Service layer.
4. Engine interfaces.
5. Job model.
6. Event model.
7. Error taxonomy.
8. Storage abstraction.

## Phase 2 — Digital Twin

1. Project hierarchy.
2. Stable object IDs.
3. Object registry.
4. Engineering graph.
5. Source references.
6. Spatial index.
7. Revision graph.

## Phase 3 — CAD/BIM Intelligence

1. Semantic CAD parser.
2. CAD object normalization.
3. IFC normalization.
4. Spatial queries.
5. Connectivity graph.
6. Advanced clash detection.
7. Safe mutation pipeline.

## Phase 4 — Engineering Intelligence

1. Standards engine.
2. Rule engine.
3. Evidence chain.
4. Engineering QA.
5. Multi-reviewer board.
6. Change impact.

## Phase 5 — QS

1. Quantity engine.
2. Specification mapping.
3. BOQ traceability.
4. Cost engine.
5. Alternatives.
6. Estimate revision diff.

## Phase 6 — AI Platform

1. Planner.
2. Model router.
3. Escalation.
4. Fallback.
5. Tool authorization.
6. Agent memory.
7. Evaluation framework.

## Phase 7 — Production SaaS

1. Next.js UI.
2. FastAPI gateway.
3. Multi-tenancy.
4. RBAC.
5. Object storage.
6. Worker infrastructure.
7. Billing.
8. Audit.
9. Observability.

## Phase 8 — Autonomous Engineering

1. Design alternatives.
2. Optimization.
3. Auto-coordination.
4. Auto-QS.
5. Impact analysis.
6. Controlled CAD/BIM mutation.
7. Human approval workflow.
8. Publish-ready deliverables.

---

# 39. Priority matrix

## P0 — Không được thiếu

- Deterministic engineering calculations
- Evidence chain
- Stable IDs
- Digital Twin core
- Revision safety
- Test suite
- Tool authorization
- Tenant isolation
- Audit logs
- Human approval

## P1 — Tạo khác biệt sản phẩm

- Semantic CAD
- BIM coordination
- Engineering Knowledge Graph
- Standards Engine
- Rule Engine
- Change Impact
- Ask the Building
- Model Router
- AI evaluation

## P2 — Tăng giá trị thương mại

- Design alternatives
- Optimization
- Cost alternatives
- Collaboration
- Advanced reporting
- Billing
- Enterprise SSO

## P3 — Future moat

- Autonomous design
- Continuous project learning
- Predictive coordination
- Construction sequence reasoning
- Digital twin simulation
- Multi-project intelligence

---

# 40. Critical architectural anti-patterns

Không được:

1. Cho LLM tự tính toán kỹ thuật.
2. Cho agent sửa CAD trực tiếp không có snapshot.
3. Dùng RAG text làm compliance engine duy nhất.
4. Dùng chat history làm database dự án.
5. Để binary file lớn trong PostgreSQL.
6. Cho mọi agent quyền gọi mọi tool.
7. Hard-code model provider vào business logic.
8. Hard-code standard version trong prompt.
9. Gộp mọi xử lý dài vào HTTP request.
10. Dùng Streamlit làm production architecture lâu dài.
11. Không có golden datasets.
12. Không có revision lineage.
13. Không có source references.
14. Không có tenant isolation.
15. Tự động publish thay đổi safety-critical.

---

# 41. North Star Workflow

Workflow mẫu phải đạt được:

```text
User uploads architectural + MEP drawings
                ↓
Document ingestion
                ↓
CAD/BIM parsing
                ↓
Semantic object extraction
                ↓
Digital Twin creation
                ↓
Engineering graph construction
                ↓
Requirement extraction
                ↓
Engineering planning
                ↓
Parallel MEP analysis
                ↓
Deterministic calculations
                ↓
Standards validation
                ↓
Clash / clearance / constructability
                ↓
Quantity takeoff
                ↓
BOQ / estimate
                ↓
Design alternatives
                ↓
Optimization
                ↓
Review Board
                ↓
Human approval
                ↓
CAD/BIM mutation
                ↓
New revision
                ↓
Impact analysis
                ↓
Reports + deliverables
```

---

# 42. Product North Star: “Ask the Building”

Hệ thống phải có khả năng trả lời câu hỏi dựa trên project state thay vì chỉ dựa vào LLM memory.

Ví dụ:

> “Tầng 3 có bao nhiêu FCU?”

> “FCU nào chưa kết nối điện?”

> “Tổng tải điện hiện tại là bao nhiêu?”

> “Có bao nhiêu clash critical?”

> “Clash nào ảnh hưởng tới maintenance?”

> “Tại sao revision 04 tăng 6.2% chi phí?”

> “Nếu di chuyển AHU-02 2 mét về phía đông thì những gì thay đổi?”

> “Tối ưu hệ HVAC để giảm CAPEX 8% nhưng không vi phạm constraints.”

Các câu trả lời phải có:

```text
Answer
 ├── Direct result
 ├── Confidence
 ├── Evidence
 ├── Calculations
 ├── Standards
 ├── Affected objects
 └── Suggested next action
```

---

# 43. Ultimate product definition

MEP-Agents Super Pro được coi là đạt mục tiêu V2 khi:

> Một kỹ sư có thể đưa toàn bộ dữ liệu dự án vào hệ thống, yêu cầu phân tích/thiết kế/kiểm tra/bóc khối lượng/dự toán, nhận kết quả có evidence và revision lineage, xem các phương án thay thế, phê duyệt thay đổi và xuất hồ sơ mà không cần phụ thuộc vào một LLM duy nhất.

Đây là mục tiêu kiến trúc; không đồng nghĩa hệ thống được phép tự động thay thế trách nhiệm của kỹ sư hoặc người phê duyệt chuyên môn.

---

# 44. Immediate next actions

Theo thứ tự:

1. Tạo branch `architecture/v2-foundation`.
2. Snapshot current behavior bằng regression tests.
3. Chuẩn hóa `domain` và `engines` interfaces.
4. Thiết kế PostgreSQL schema cho Project/Digital Twin.
5. Thiết kế stable object ID và source references.
6. Thiết kế Job/Event contracts.
7. Xây Evidence model.
8. Xây Standards/Rule interfaces.
9. Xây semantic CAD object model.
10. Xây Engineering Knowledge Graph abstraction.
11. Tách agent orchestration khỏi domain calculations.
12. Thiết lập benchmark/evaluation dataset.
13. Xây Review Board contract.
14. Sau khi core ổn định mới chuyển production UI sang Next.js.

---

# 45. Acceptance criteria cho V2 Foundation

V2 Foundation được chấp nhận khi:

- [ ] Một project có stable ID và revision lineage.
- [ ] Một CAD/BIM object có source reference.
- [ ] Một calculation có input/result/formula/standard/evidence.
- [ ] Một agent không thể gọi tool ngoài permission.
- [ ] Một long-running job có trạng thái và retry.
- [ ] Một revision có diff.
- [ ] Một BOQ item truy ngược được về source objects.
- [ ] Một compliance result truy ngược được về rule/standard.
- [ ] Một model call được trace với cost/latency.
- [ ] Có golden regression suite.
- [ ] Có tenant isolation test.
- [ ] Có approval workflow cho mutation.
- [ ] CI kiểm tra tests/type/security cơ bản.

---

# 46. Kết luận

MEP-Agents không nên được rewrite thành một chatbot lớn hơn. Hướng phát triển đúng là **tiến hóa từ multi-agent prototype thành một engineering platform có state, graph, deterministic engines và evidence**.

Kiến trúc mục tiêu:

```text
              AI AGENTS
                  │
                  ▼
           ORCHESTRATION
                  │
                  ▼
        ENGINEERING KNOWLEDGE
                  │
          ┌───────┴────────┐
          ▼                ▼
    DIGITAL TWIN       RULE/STD
          │                │
          └───────┬────────┘
                  ▼
       DETERMINISTIC ENGINES
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
      CAD        BIM        QS
       │          │          │
       └──────────┼──────────┘
                  ▼
          REVIEW + EVIDENCE
                  │
                  ▼
          HUMAN APPROVAL
                  │
                  ▼
        VERSIONED DELIVERABLE
```

**Nguyên tắc cuối cùng:** AI có thể lập kế hoạch và suy luận; engineering engines phải tính; rules phải kiểm tra; graph phải giữ sự thật của dự án; evidence phải giải thích được kết quả; revision phải bảo toàn lịch sử; con người phải kiểm soát các quyết định có rủi ro cao.

---

## Appendix A — Suggested first GitHub epics

1. `EPIC-001 Architecture V2 Foundation`
2. `EPIC-002 Domain Model & Digital Twin`
3. `EPIC-003 Engineering Knowledge Graph`
4. `EPIC-004 CAD Semantic Intelligence`
5. `EPIC-005 BIM Intelligence & Coordination`
6. `EPIC-006 Standards & Rule Engine`
7. `EPIC-007 Engineering Calculation Platform`
8. `EPIC-008 Evidence & Audit`
9. `EPIC-009 Revision & Change Impact`
10. `EPIC-010 Quantity / BOQ / Cost Intelligence`
11. `EPIC-011 AI Orchestrator & Model Router`
12. `EPIC-012 Review Board & Human Approval`
13. `EPIC-013 Evaluation / Golden Dataset`
14. `EPIC-014 Production SaaS / Multi-tenancy`
15. `EPIC-015 Web Workspace`
16. `EPIC-016 Optimization & Design Alternatives`
17. `EPIC-017 Enterprise Security`
18. `EPIC-018 Observability / SRE`
19. `EPIC-019 Autonomous Engineering Workflows`
20. `EPIC-020 Release / Deployment / Operations`

---

## Appendix B — Guiding statement

> **Build the source of truth first. Put intelligence on top of it. Never make the LLM the source of truth.**
