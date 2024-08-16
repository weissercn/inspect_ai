// @ts-check
import { html } from "htm/preact";
import { ApplicationIcons } from "../../../appearance/Icons.mjs";
/**
 * Renders a view displaying a list of state changes.
 *
 * @param {Object} props - The properties for the component.
 * @param {import("../../../types/log").Changes} props.changes - The list of changes to be displayed.
 * @param {Record<string, string>} [props.style] - Optional custom styles for the view container.
 * @returns {import("preact").JSX.Element | undefined} The component.
 */
export const StateDiffView = ({ changes, style }) => {
  const mutations = changes.map((change) => {
    // Compute the change rows
    const symbol = iconForOp(change.op);
    const color = colorForOp(change.op);
    const toStyle = {};
    const baseStyle = {
      color,
    };
    return html`
      <div style=${baseStyle}>${symbol ? symbol : ""}</div>
      <code style=${{ padding: "0", ...baseStyle }}>${change.path}</code>
      <div style=${toStyle}>${renderValue(change)}</div>
    `;
  });

  return html`<div
    style=${{
      display: "grid",
      gridTemplateColumns: "max-content max-content 1fr",
      columnGap: "1em",
      rowGap: 0,
      ...style,
    }}
  >
    ${mutations}
  </div>`;
};

/**
 * Returns a symbol representing the operation type.
 *
 * @param {string} op - The operation type.
 * @returns {import("preact").JSX.Element | undefined} The component.
 */
const iconForOp = (op) => {
  switch (op) {
    case "add":
      return html`<i class="${ApplicationIcons.changes.add}" />`;
    case "remove":
      return html`<i class="${ApplicationIcons.changes.remove}" />`;
    case "replace":
      return html`<i class="${ApplicationIcons.changes.replace}" />`;
    case "copy":
    case "move":
    case "test":
    default:
      return undefined;
  }
};

/**
 * Returns a background color configuration based on the operation type.
 *
 * @param {string} op - The operation type.
 * @returns {string|undefined} - The color configuration, or undefined for certain operations.
 */
const colorForOp = (op) => {
  switch (op) {
    case "add":
      return "var(--bs-success)";
    case "remove":
      return "var(--bs-danger)";
    case "replace":
      return "var(--bs-success)";
    case "copy":
    case "move":
    case "test":
    default:
      return undefined;
  }
};

/**
 * Renders the value of a change based on its type.
 *
 * @param {import("../../../types/log").JsonChange} change - The change object containing the value.
 * @returns {import("preact").JSX.Element|Object|string} - The rendered HTML template if the value is an object with content and source, otherwise the value itself.
 */
const renderValue = (change) => {
  const contents =
    typeof change.value === "object" || Array.isArray(change.value)
      ? JSON.stringify(change.value, null, 2)
      : typeof change.value === "string"
        ? change.value.trim()
        : change.value;

  return html`<pre
    style=${{
      whiteSpace: "pre-wrap",
      wordBreak: "break-word",
      marginBottom: "0",
    }}
  >
  ${contents || ""}</pre
  >`;
};