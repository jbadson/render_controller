import React, { Component } from 'react';
import './JobInput.css';
import axios from "axios";
import { FileBrowserPopup } from './FileBrowser';


/**
 * Number input field that changes CSS className if value contains a non-digit.
 * @prop {string} name: Name attribute of HTML input
 * @prop {string} label: Label text
 * @prop {int} value: Contents of input field.
 * @prop {function} onChange - Callback on input change.
 */
class NumberInput extends Component {
  constructor(props) {
    super(props);
    this.classNameOk = "number-input-field";
    this.classNameBad = "number-input-field-bad";
    this.state = {
      className: this.classNameOk
    }
    this.handleChange = this.handleChange.bind(this);
  }

  handleChange(event) {
    let className = this.classNameOk;
    if (isNaN(event.target.value)) {
      className = this.classNameBad;
    }
    this.setState({
      className: className,
    });
    this.props.onChange(event);
  }

  render() {
    return (
      <label className="input-block">
        {this.props.label || ""}
        <input type="text"
          name={this.props.name}
          className={this.state.className}
          value={this.props.value}
          onChange={this.handleChange}
        />
      </label>
    )
  }
}

/**
 * @prop {boolean} checked -- Is node checked (active) ?
 * @prop {string} name -- Node name (used as button text)
 */
function NodeBox(props) {
  let className = "input-nodebox";
  if (props.checked) {
    className += "-checked";
  }
  return (
    <div className={className} onClick={() => props.onClick(props.name)}>
      {props.name}
    </div>
  )
}

function LeftCheckBox(props) {
  return (
    <label className={props.className}>
      <input
        type="checkbox"
        className={props.className}
        checked={props.checked}
        onChange={props.onChange}
      />
      {props.label}
    </label>
  )
}

/**
 * Widget for selecting render nodes.
 * @prop {Array} renderNodes - Array of objects describing render nodes.
 * @prop {Array} nodesEnabled - Array of objects describing enabled render nodes.
 * @prop {boolean} useAll - Use all render nodes?
 * @prop {callback} onSelectAll - Function to call if select all is clicked
 * @prop {callback} onSelectNone - Function to call if select none is clicked
 * @prop {callback} onCheckNode - Function to call if node button is checked
 */
function NodePicker(props) {
  return (
    <div className="np-container">
    <ul>
      <li className="input-row">
        <p className="input-header2">Render nodes</p>
      </li>
      <li className="input-row">
        <div className="center">
          <LeftCheckBox
            className="ip-checkbox"
            label="Use all"
            checked={props.useAll}
            onChange={props.useAll ? props.onSelectNone : props.onSelectAll}
          />
        </div>
      </li>
      { props.useAll ||
      <li className="input-row">
        {props.renderNodes.map(name => {
          let isChecked = false;
          if (props.renderNodes.includes(name) && props.nodesEnabled.includes(name)) {
            isChecked = true;
          }
          return (
              <NodeBox
                key={name}
                name={name}
                checked={isChecked}
                onClick={props.onCheckNode}
              />
          )
        })}
      </li>
    }
    </ul>
    </div>
  )
}


/**
 * Job input widget.
 * @prop {function} onSubmit - Called when input is submitted.
 * @prop {string} path - Initial path to set in browser.
 * @prop {Array<string>} renderNodes - Array of all render nodes available on server.
 * @prop {int} startFrame - Optional: Value to set in start frame field.
 * @prop {int} endFrame - Optional: Value to set in end frame field.
 * @prop {Array<string>} nodesEnabled - Optional: List of enabled render nodes.
 */
class JobInput extends Component {
  constructor(props) {
    super(props);
    let useAllNodes = false;
    let nodesEnabled = props.nodesEnabled;
    if (nodesEnabled === undefined) {
      useAllNodes = true;
      nodesEnabled = props.renderNodes;
    } else if (props.renderNodes.length === nodesEnabled.length) {
      useAllNodes = true;
    }
    this.state = {
      path: props.path || '',
      startFrame: props.startFrame || '',
      endFrame: props.endFrame || '',
      renderNodes: props.renderNodes,
      nodesEnabled: nodesEnabled,
      useAllNodes: useAllNodes,
      showBrowser: false,
    }
    this.toggleBrowser = this.toggleBrowser.bind(this);
    this.setPath = this.setPath.bind(this);
    this.selectAllNodes = this.selectAllNodes.bind(this);
    this.deselectAllNodes = this.deselectAllNodes.bind(this);
    this.setNodeState = this.setNodeState.bind(this);
    this.handleChange = this.handleChange.bind(this);
    this.submit = this.submit.bind(this);
  }

  toggleBrowser() {
    this.setState(state => ({showBrowser: !state.showBrowser}));
  }

  setPath(path) {
    this.setState({
      path: path,
      showBrowser: false,
    });
  }

  selectAllNodes() {
    this.setState({ nodesEnabled: this.state.renderNodes, useAllNodes: true });
  }

  deselectAllNodes() {
    this.setState({ nodesEnabled: [], useAllNodes: false });
  }

  setNodeState(node) {
    const nodesEnabled = this.state.nodesEnabled;
    let updatedNodes = [];
    if (nodesEnabled.includes(node)) {
      updatedNodes = nodesEnabled.filter((n) => { return n !== node });
    } else {
      updatedNodes = nodesEnabled;
      updatedNodes.push(node);
    }
    this.setState({nodesEnabled: updatedNodes});
  }

  handleChange(event) {
    this.setState({[event.target.name]: event.target.value});
  }

  submit() {
    const { path, startFrame, endFrame, renderNodes, nodesEnabled, useAllNodes } = this.state;

    // Validate inputs
    if (!startFrame || isNaN(startFrame)) {
      alert("Start frame must be a number.");
      return;
    }
    if (!endFrame || isNaN(endFrame)) {
      alert("End frame must be a number.");
      return;
    }

    // Get list of selected nodes.
    let selectedNodes = [];
    if (useAllNodes) {
      selectedNodes = renderNodes;
    } else {
      selectedNodes = nodesEnabled;
    }

    const ret = {
      path: path,
      start_frame: startFrame,
      end_frame: endFrame,
      nodes: selectedNodes
    }
    axios.post(process.env.REACT_APP_BACKEND_API + "/job/new", ret)
      .then(
        result => {this.props.onClose(result.data)},
        error => {console.error(error)}
      )
  }

  renderNodePicker() {
    return (
      <NodePicker
        renderNodes={this.state.renderNodes}
        nodesEnabled={this.state.nodesEnabled}
        useAll={this.state.useAllNodes}
        onCheckNode={this.setNodeState}
        onSelectAll={this.selectAllNodes}
        onSelectNone={this.deselectAllNodes}
      />
    )
  }

  renderInputPane() {
    return (
      <ul>
        <li className="layout-row">
          <label className="input-block">
            Project file:
            <input
              type="text"
              name="path"
              className="txt-path"
              value={this.state.path}
              onChange={this.handleChange}
            />
            <input
              type="button"
              className="sm-button"
              value="Browse"
              onClick={this.toggleBrowser}
            />
          </label>
        </li>
        <li className="layout-row">
          <NumberInput
            name="startFrame"
            label="Start frame: "
            value={this.state.startFrame}
            onChange={this.handleChange}
          />
          <NumberInput
            name="endFrame"
            label="End frame: "
            value={this.state.endFrame}
            onChange={this.handleChange}
          />
        </li>
        <li className="layout-row">
          {this.renderNodePicker()}
        </li>
        <li className="layout-row">
          <div className="center">
            <button className="sm-button" onClick={this.submit} >OK</button>
            <button className="sm-button" onClick={this.props.onClose} >Cancel</button>
          </div>
        </li>
      </ul>
    )
  }

  render() {
    if (!this.state.renderNodes) {
      return <p>Loading...</p>
    }
    return (
      <div className="input-container">
        {this.state.showBrowser &&
          <FileBrowserPopup
            path={this.props.path}
            onClose={this.toggleBrowser}
            onFileClick={this.setPath}
          />
        }
        <ul>
          <li className="input-row">
            <div className="input-header">New Render Job</div>
          </li>
          <li className="input-row">
            <div className="input-inner">
              {this.renderInputPane()}
            </div>
          </li>
        </ul>
      </div>
    )
  }
}

export default JobInput;
