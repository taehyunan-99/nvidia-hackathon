import { PluginContext } from "molstar/lib/mol-plugin/context";
import { DefaultPluginSpec } from "molstar/lib/mol-plugin/spec";
import { MolScriptBuilder as Q } from "molstar/lib/mol-script/language/builder";
import { Structure } from "molstar/lib/mol-model/structure";
import { Color } from "molstar/lib/mol-util/color";
export type ViewOptions = {
  view: "overview" | "contacts" | "context";
  opacity: number;
  hideAntibody: boolean;
  context: boolean;
};
export async function createMolecularViewer(
  canvas: HTMLCanvasElement,
  host: HTMLDivElement,
) {
  const plugin = new PluginContext(DefaultPluginSpec());
  await plugin.init();
  if (!(await plugin.initViewerAsync(canvas, host))) {
    plugin.dispose();
    throw new Error("WebGL을 사용할 수 없습니다.");
  }
  plugin.canvas3d?.setProps({
    renderer: { backgroundColor: Color(0xffffff) },
    camera: { helper: { axes: { name: "off", params: {} } } },
  });
  return plugin;
}
export async function loadMolecule(
  plugin: PluginContext,
  cif: string,
  pdb: string,
  mode: string,
  residues: { chain: string; seq: number }[],
  chainIds?: string[],
  contextChainIds?: string[],
) {
  const data = await plugin.builders.data.rawData({ data: cif, label: pdb });
  const trajectory = await plugin.builders.structure.parseTrajectory(
    data,
    "mmcif",
  );
  const model = await plugin.builders.structure.createModel(trajectory);
  // 예측 구조에는 assembly 정의가 없어 모델을 그대로 사용한다.
  const structure = chainIds
    ? await plugin.builders.structure.createStructure(model, { name: "model", params: {} })
    : await plugin.builders.structure.createStructure(model, {
        name: "assembly",
        params: { id: "1" },
      });
  const chains = chainIds ?? (pdb === "1N8Z" ? ["C", "B", "A"] : ["A", "D", "C"]);
  const colors = [0x259c91, 0xe99032, 0x7d6bd0];
  const chainQuery = (chain: string) =>
    Q.struct.generator.atomGroups({
      "chain-test": Q.core.rel.eq([
        Q.struct.atomProperty.macromolecular.label_asym_id(),
        chain,
      ]),
    });
  const components = await Promise.all(
    chains.map((c) =>
      plugin.builders.structure.tryCreateComponentFromExpression(
        structure,
        chainQuery(c),
        "chain-" + c,
      ),
    ),
  );
  type Representation = Awaited<
    ReturnType<
      typeof plugin.builders.structure.representation.addRepresentation
    >
  >;
  const reps: Representation[] = [];
  for (let i = 0; i < components.length; i++) {
    const component = components[i];
    if (!component?.obj) throw new Error("사슬 대응을 확인할 수 없습니다.");
    reps.push(
      await plugin.builders.structure.representation.addRepresentation(
        component,
        {
          type:
            mode === "surface" || (mode === "mixed" && i === 0)
              ? "molecular-surface"
              : "cartoon",
          typeParams: { alpha: 1 },
          color: "uniform",
          colorParams: { value: Color(colors[i]) },
        },
      ),
    );
  }
  const context =
    await plugin.builders.structure.tryCreateComponentFromExpression(
      structure,
      Q.struct.generator.atomGroups({
        "chain-test": contextChainIds ? Q.core.set.has([Q.set(...contextChainIds), Q.struct.atomProperty.macromolecular.label_asym_id()]) : Q.core.logic.not([
          Q.core.set.has([
            Q.set(...chains),
            Q.struct.atomProperty.macromolecular.label_asym_id(),
          ]),
        ]),
        "residue-test": Q.core.rel.neq([
          Q.struct.atomProperty.macromolecular.label_comp_id(),
          "HOH",
        ]),
      }),
      "context",
    );
  const contextRep = context?.obj
    ? await plugin.builders.structure.representation.addRepresentation(
        context,
        {
          type: "ball-and-stick",
          color: "uniform",
          colorParams: { value: Color(0xb21a91) },
          typeParams: { alpha: 0, sizeFactor: 0.5 },
        },
      )
    : undefined;
  const contextLoci = context?.obj
    ? Structure.toStructureElementLoci(context.obj.data)
    : undefined;
  const contactComponents = [];
  const contactReps: Representation[] = [];
  for (let i = 0; i < chains.length; i++) {
    const rs = residues.filter((r) => r.chain === chains[i]);
    const expression = Q.struct.combinator.merge(
      rs.map((r) =>
        Q.struct.generator.atomGroups({
          "chain-test": Q.core.rel.eq([
            Q.struct.atomProperty.macromolecular.label_asym_id(),
            r.chain,
          ]),
          "residue-test": Q.core.rel.eq([
            Q.struct.atomProperty.macromolecular.label_seq_id(),
            r.seq,
          ]),
        }),
      ),
    );
    const c = await plugin.builders.structure.tryCreateComponentFromExpression(
      structure,
      expression,
      "contacts-" + chains[i],
    );
    if (!c?.obj || c.obj.data.polymerResidueCount !== rs.length)
      throw new Error("근접 잔기 대응 수가 일치하지 않습니다.");
    contactComponents.push(c);
    contactReps.push(
      await plugin.builders.structure.representation.addRepresentation(c, {
        type: "ball-and-stick",
        color: "uniform",
        colorParams: { value: Color(colors[i]) },
        typeParams: { alpha: 0, sizeFactor: 0.35 },
      }),
    );
  }
  const fullLoci = components.map((c) =>
    Structure.toStructureElementLoci(c!.obj!.data),
  );
  const contactLoci = contactComponents.map((c) =>
    Structure.toStructureElementLoci(c.obj!.data),
  );
  let options: ViewOptions = {
    view: "overview",
    opacity: 1,
    hideAntibody: false,
    context: false,
  };
  let queue = Promise.resolve();
  const update = (next: ViewOptions, focus = false) => {
    queue = queue.then(async () => {
      options = next;
      const dim = next.view !== "overview";
      const state = plugin.build();
      reps.forEach((r, i) =>
        state.to(r).update((old) => {
          old.type.params.alpha =
            i === 0
              ? next.opacity * (dim ? 0.12 : 1)
              : next.hideAntibody
                ? 0
                : dim
                  ? 0.08
                  : 1;
        }),
      );
      contactReps.forEach((r, i) =>
        state.to(r).update((old) => {
          old.type.params.alpha =
            next.view === "contacts" && (i === 0 || !next.hideAntibody) ? 1 : 0;
        }),
      );
      if (contextRep)
        state.to(contextRep).update((old) => {
          old.type.params.alpha = next.context ? 1 : 0;
        });
      await state.commit();
      if (focus) {
        const durationMs = matchMedia("(prefers-reduced-motion: reduce)")
          .matches
          ? 0
          : 650;
        const loci =
          next.view === "context" && contextLoci
            ? contextLoci
            : next.view === "contacts"
              ? next.hideAntibody
                ? contactLoci.slice(0, 1)
                : contactLoci
              : next.hideAntibody
                ? fullLoci.slice(0, 1)
                : fullLoci;
        plugin.managers.camera.focusLoci(loci, {
          durationMs,
          minRadius: next.view === "overview" ? 25 : 12,
          extraRadius: next.view === "overview" ? 10 : 6,
          optimizeDirection: true,
        });
      }
      plugin.canvas3d?.requestDraw();
    });
    return queue;
  };
  return {
    update,
    count: residues.length,
    hasContext: !!contextRep,
  };
}
