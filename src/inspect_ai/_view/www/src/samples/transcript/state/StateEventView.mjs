// @ts-check
import { html } from "htm/preact";

import { EventPanel } from "../EventPanel.mjs";
import { RenderableChangeTypes } from "./StateEventRenderers.mjs";
import { StateDiffView } from "./StateDiffView.mjs";

/**
 * Renders the StateEventView component.
 *
 * @param {Object} props - The properties passed to the component.
 * @param { string  } props.id - The id of this event.
 * @param {import("../../../types/log").StateEvent } props.event - The event object to display.
 * @param {import("../TranscriptState.mjs").StateManager} props.stateManager - A function that updates the state with a new state object.
 * @returns {import("preact").JSX.Element} The component.
 */
export const StateEventView = ({ id, event, stateManager }) => {
  const resolvedState = stateManager.applyChanges(event.changes);

  const tabs = [
    html`<${StateDiffView} changes=${event.changes} name="Diffs" />`,
  ];
  const changePreview = generatePreview(event.changes, resolvedState);
  if (changePreview) {
    tabs.unshift(html`<div name="Summary">${changePreview}</div>`);
  }

  // Compute the title
  const title = event.event === "state" ? "State Updated" : "Store Updated";
  return html`
  <${EventPanel} id=${id} title=${title} collapse=${changePreview === undefined ? true : undefined}>
    ${tabs}
  </${EventPanel}>`;
};

/**
 * Renders the value of a change based on its type.
 *
 * @param {import("../../../types/log").JsonChange[]} changes - The change object containing the value.
 * @param {Object} resolvedState - The change object containing the value.
 * @returns {import("preact").JSX.Element|Object|string|undefined} - The rendered HTML template if the value is an object with content and source, otherwise the value itself.
 */
const generatePreview = (changes, resolvedState) => {
  for (const changeType of RenderableChangeTypes) {
    const requiredMatchCount =
      changeType.signature.remove.length +
      changeType.signature.replace.length +
      changeType.signature.add.length;
    let matchingOps = 0;
    for (const change of changes) {
      if (
        changeType.signature.remove.includes(change.path) ||
        changeType.signature.replace.includes(change.path) ||
        changeType.signature.add.includes(change.path)
      ) {
        matchingOps++;
      }
      if (matchingOps === requiredMatchCount) {
        return changeType.render(resolvedState);
      }
    }
  }
  return undefined;
};