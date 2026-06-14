from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from know_code.cluster import capability_facts, cluster_facts, render_clusters_markdown
from know_code.cli import main
from know_code.config import load_workspace_config, write_default_config
from know_code.global_graph import build_global_graph
from know_code.graph import diff_facts, facts_for_operation
from know_code.planner import generate_plan
from know_code.quality import analyze_quality, render_quality_report
from know_code.scanner import scan_repositories
from know_code.visualize import build_visualization_graph, write_visualization


class ScanTests(unittest.TestCase):
    def test_scan_custom_framework_and_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = root / "subscription-service"
            android = root / "android-app"
            h5 = root / "h5-member-center"
            proto = root / "contracts"
            service.mkdir()
            android.mkdir()
            h5.mkdir()
            proto.mkdir()

            write(
                service / "src/main/java/CancelSubscriptionHandler.java",
                """
                @BizService("subscription")
                class CancelSubscriptionHandler {
                  @BizAction("cancel")
                  CancelResp cancel(CancelReq req) {
                    kafkaTemplate.send("subscription.cancelled", req.id());
                    return new CancelResp();
                  }
                }
                """,
            )
            write(
                android / "app/src/main/java/SubscriptionRepository.kt",
                """
                interface SubscriptionApi {
                  @POST("/subscriptions/{id}/cancel")
                  fun cancel(): Call<Unit>
                }
                class SubscriptionRepository {
                  fun cancel() = bizClient.call("subscription.cancel", request)
                }
                """,
            )
            write(
                h5 / "src/subscription.ts",
                """
                export const routes = [{ path: "/account/subscription" }]
                export function cancel() {
                  return request.post("/subscriptions/123/cancel", {})
                }
                """,
            )
            write(
                proto / "subscription.proto",
                """
                syntax = "proto3";
                package subscription.v1;
                service SubscriptionService {
                  rpc CancelSubscription(CancelSubscriptionRequest) returns (CancelSubscriptionResponse);
                }
                message CancelSubscriptionRequest {}
                message CancelSubscriptionResponse {}
                """,
            )
            adapter_config = root / "framework-adapters.json"
            adapter_config.write_text(
                json.dumps(
                    {
                        "adapters": [
                            {
                                "name": "company-biz-http",
                                "provider_annotations": {
                                    "service": "BizService",
                                    "action": "BizAction",
                                },
                                "client_call_regexes": [
                                    r"bizClient\.call\(\s*\"(?P<operation>[A-Za-z0-9_.:-]+)\""
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            facts = scan_repositories([service, android, h5, proto], adapter_config)
            pairs = {(fact.predicate, fact.object) for fact in facts}
            self.assertIn(("provides_operation", "operation:subscription.cancel"), pairs)
            self.assertIn(("calls_operation", "operation:subscription.cancel"), pairs)
            self.assertIn(("calls_api", "api:POST /subscriptions/{id}/cancel"), pairs)
            self.assertIn(("calls_api", "api:POST /subscriptions/123/cancel"), pairs)
            self.assertIn(("provides_rpc", "rpc:subscription.v1.SubscriptionService.CancelSubscription"), pairs)

            operation_facts = facts_for_operation(facts, "subscription.cancel")
            self.assertGreaterEqual(len(operation_facts), 2)

            prd = root / "prd.md"
            prd.write_text("Users can cancel subscription from the member page.", encoding="utf-8")
            plan = generate_plan(prd, facts)
            self.assertIn("subscription-service", plan)
            self.assertIn("android-app", plan)
            self.assertIn("subscription.cancel", plan)

            graph = build_visualization_graph(facts)
            self.assertGreaterEqual(graph["stats"]["nodes"], 4)
            self.assertGreaterEqual(graph["stats"]["edges"], 4)

            html_path = root / "graph.html"
            write_visualization(facts, html_path)
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("Know Code Graph", html)
            self.assertIn("subscription.cancel", html)

    def test_diff_detects_added_and_removed_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "h5"
            repo.mkdir()
            source = repo / "src/api.ts"
            write(source, "export const a = () => request.post(\"/a\", {})")
            first = scan_repositories([repo])
            write(source, "export const b = () => request.post(\"/b\", {})")
            second = scan_repositories([repo])

            diff = diff_facts(first, second)
            self.assertEqual(len(diff["added"]), 1)
            self.assertEqual(len(diff["removed"]), 1)

    def test_cpp_modules_and_interfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "render-engine"
            repo.mkdir()
            write(
                repo / "CMakeLists.txt",
                """
                add_library(render_core src/render.cpp)
                add_executable(render_tool src/main.cpp)
                """,
            )
            write(
                repo / "include/Renderer.hpp",
                """
                class Renderer {
                public:
                  void draw();
                };
                """,
            )
            write(
                repo / "src/render.cpp",
                """
                void CloseHandle();
                void draw_frame() {}
                void render_scene() {
                  CloseHandle();
                  draw_frame();
                }
                """,
            )

            facts = scan_repositories([repo])
            pairs = {(fact.predicate, fact.object) for fact in facts}
            self.assertIn(("defines_module", "module:render-engine:render_core"), pairs)
            self.assertIn(("defines_module", "module:render-engine:render_tool"), pairs)
            self.assertIn(("defines_interface", "interface:render-engine:Renderer"), pairs)
            self.assertIn(("belongs_to_module", "module:render-engine:render_core"), pairs)
            self.assertIn(("provides_operation", "operation:cpp.draw_frame"), pairs)
            self.assertIn(("provides_operation", "operation:cpp.render_scene"), pairs)
            self.assertIn(("calls_operation", "operation:cpp.draw_frame"), pairs)
            self.assertNotIn(("provides_operation", "operation:cpp.CloseHandle"), pairs)
            self.assertNotIn(("calls_operation", "operation:cpp.CloseHandle"), pairs)

    def test_hierarchical_capability_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "native-app"
            repo.mkdir()
            write(
                repo / "CMakeLists.txt",
                """
                add_library(core src/core.cpp)
                add_executable(app app/main.cpp app/extra.cpp)
                """,
            )
            write(
                repo / "src/core.cpp",
                """
                void core_compute() {}
                """,
            )
            write(
                repo / "app/main.cpp",
                """
                void app_run() {
                  core_compute();
                }
                """,
            )
            write(
                repo / "app/extra.cpp",
                """
                void app_extra() {
                  core_compute();
                }
                """,
            )

            facts = scan_repositories([repo])
            clusters = cluster_facts(facts, min_nodes=2, strategy="hierarchical")
            self.assertGreaterEqual(len(clusters), 2)

            derived = capability_facts(clusters, repo="native-app", commit="derived", base_facts=facts)
            dependency_edges = [fact for fact in derived if fact.predicate == "capability_depends_on"]
            self.assertTrue(dependency_edges)
            self.assertTrue(
                any("cpp.core_compute" in fact.attributes.get("sample_operations", []) for fact in dependency_edges)
            )

    def test_global_graph_connects_repositories_by_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            web = root / "member-h5"
            service = root / "subscription-service"
            out_dir = root / "out"
            web.mkdir()
            service.mkdir()
            write(
                web / "src/subscription.ts",
                """
                export function cancelSubscription() {
                  return request.post("/subscriptions/cancel", {})
                }
                """,
            )
            write(
                service / "src/main/java/SubscriptionController.java",
                """
                class SubscriptionController {
                  @PostMapping("/subscriptions/cancel")
                  void cancel() {}
                }
                """,
            )

            manifest = build_global_graph([web, service], out_dir, strategy="hierarchical", min_nodes=1)
            self.assertTrue(Path(manifest["outputs"]["raw_facts"]).exists())
            self.assertTrue(Path(manifest["outputs"]["serving_graph"]).exists())
            self.assertIn("member-h5", manifest["outputs"]["repo_outputs"])
            self.assertIn("subscription-service", manifest["outputs"]["repo_outputs"])

            augmented = Path(manifest["outputs"]["augmented_facts"]).read_text(encoding="utf-8")
            self.assertIn("capability_depends_on", augmented)
            self.assertIn("api:POST /subscriptions/cancel", augmented)

    def test_workspace_config_and_index_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "service"
            repo.mkdir()
            write(
                repo / "src/main/java/HealthController.java",
                """
                class HealthController {
                  @GetMapping("/health")
                  String health() { return "ok"; }
                }
                """,
            )
            config = root / ".know-code.yml"
            write_default_config(config)
            config.write_text(
                """
                output: graph-out
                strategy: hierarchical
                min_nodes: 1
                title: Test Workspace
                repos:
                  - path: service
                    name: service
                """,
                encoding="utf-8",
            )
            loaded = load_workspace_config(config)
            self.assertEqual(loaded.repos, [repo.resolve()])
            exit_code = main(["index", "--config", str(config)])
            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "graph-out" / "manifest.json").exists())
            self.assertTrue((root / "graph-out" / "global.serving.html").exists())
            self.assertEqual(main(["doctor", "--config", str(config)]), 0)

    def test_init_command_accepts_repo_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_a = root / "repo-a"
            repo_b = root / "repo-b"
            repo_a.mkdir()
            repo_b.mkdir()
            config = root / ".know-code.yml"

            exit_code = main(["init", str(repo_a), str(repo_b), "--config", str(config)])

            self.assertEqual(exit_code, 0)
            text = config.read_text(encoding="utf-8")
            self.assertIn("path: repo-a", text)
            self.assertIn("name: repo-a", text)
            self.assertIn("path: repo-b", text)
            self.assertIn("name: repo-b", text)
            loaded = load_workspace_config(config)
            self.assertEqual(loaded.repos, [repo_a.resolve(), repo_b.resolve()])

    def test_electron_ipc_and_trpc_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "desktop-app"
            repo.mkdir()
            write(
                repo / "src/preload/index.ts",
                """
                const desktopApi = {
                  windowMinimize: () => ipcRenderer.invoke("window:minimize"),
                }
                trpc.projects.list.useQuery()
                """,
            )
            write(
                repo / "src/main/windows/main.ts",
                """
                ipcMain.handle("window:minimize", () => undefined)
                """,
            )
            write(
                repo / "src/main/lib/trpc/routers/projects.ts",
                """
                export const projectsRouter = router({
                  list: publicProcedure.query(async () => []),
                  create: publicProcedure.mutation(async () => ({})),
                })
                """,
            )

            facts = scan_repositories([repo])
            pairs = {(fact.predicate, fact.object) for fact in facts}
            self.assertIn(("calls_operation", "operation:ipc.window.minimize"), pairs)
            self.assertIn(("provides_operation", "operation:ipc.window.minimize"), pairs)
            self.assertIn(("provides_operation", "operation:desktopApi.windowMinimize"), pairs)
            self.assertIn(("maps_operation_to_operation", "operation:ipc.window.minimize"), pairs)
            self.assertIn(("calls_operation", "operation:trpc.projects.list"), pairs)
            self.assertIn(("provides_operation", "operation:trpc.projects.list"), pairs)
            self.assertIn(("provides_operation", "operation:trpc.projects.create"), pairs)

            quality = analyze_quality(facts)
            report = render_quality_report(quality)
            self.assertIn("Provider match rate", report)
            self.assertGreaterEqual(quality.operations_with_provider_and_caller, 2)

    def test_trpc_flattened_router_alias_and_surface_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "desktop-app"
            repo.mkdir()
            write(
                repo / "src/main/lib/trpc/routers/index.ts",
                """
                export function createAppRouter() {
                  return router({
                    changes: createGitRouter(),
                  })
                }
                """,
            )
            write(
                repo / "src/main/lib/git/index.ts",
                """
                export const createGitRouter = () => {
                  return router({
                    ...createStatusRouter()._def.procedures,
                  })
                }
                """,
            )
            write(
                repo / "src/main/lib/git/status.ts",
                """
                export const createStatusRouter = () => {
                  return router({
                    getStatus: publicProcedure.query(async () => ({})),
                  })
                }
                """,
            )
            write(
                repo / "src/renderer/features/changes/changes-view.tsx",
                """
                export function ChangesView() {
                  trpc.changes.getStatus.useQuery()
                  return null
                }
                """,
            )

            facts = scan_repositories([repo])
            pairs = {(fact.subject, fact.predicate, fact.object) for fact in facts}
            self.assertIn(
                (
                    "repo:desktop-app:file:src/main/lib/git/status.ts",
                    "provides_operation",
                    "operation:trpc.changes.getStatus",
                ),
                pairs,
            )
            self.assertIn(
                (
                    "screen:desktop-app:changes.ChangesView",
                    "calls_operation",
                    "operation:trpc.changes.getStatus",
                ),
                pairs,
            )
            self.assertIn(
                (
                    "screen:desktop-app:changes.ChangesView",
                    "belongs_to_module",
                    "module:desktop-app:changes",
                ),
                pairs,
            )

            clusters = cluster_facts(facts, min_nodes=2)
            markdown = render_clusters_markdown(clusters)
            self.assertIn("Changes", markdown)
            self.assertTrue(any("trpc.changes.getStatus" in cluster.operations for cluster in clusters))

            derived = capability_facts(clusters, repo="desktop-app", commit="derived")
            derived_pairs = {(fact.subject, fact.predicate, fact.object) for fact in derived}
            capability_subjects = {fact.subject for fact in derived if fact.subject.startswith("capability:")}
            self.assertTrue(capability_subjects)
            self.assertTrue(
                any(
                    predicate == "capability_has_operation"
                    and object_ == "operation:trpc.changes.getStatus"
                    for _, predicate, object_ in derived_pairs
                )
            )
            self.assertTrue(any(predicate == "is_capability" for _, predicate, _ in derived_pairs))

            compact_graph = build_visualization_graph(facts + derived, profile="capability")
            self.assertEqual(compact_graph["stats"]["profile"], "capability")
            self.assertLess(compact_graph["stats"]["edges"], build_visualization_graph(facts + derived)["stats"]["edges"])
            self.assertTrue(
                all(
                    edge["predicate"].startswith("capability_") or edge["predicate"] == "is_capability"
                    for edge in compact_graph["edges"]
                )
            )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
