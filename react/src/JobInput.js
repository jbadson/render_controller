import React, { Component } from 'react';
import './JobInput.css';
import axios from "axios";
import { FileBrowserPopup } from './FileBrowser';


/**
 * Number input field that changes CSS className if value contains a non-digit.
 * @param {string} name: Name attribute of HTML input
 * @param {string} label: Label text
 * @param {int} value: Contents of input field.
 * @param {function} onChange - Callback on input change.
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
 * @param {boolean} checked -- Is node checked (active) ?
 * @param {string} name -- Node name (used as button text)
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
 * @param {Array} renderNodes - Array of objects describing render nodes.
 * @param {Array} nodesEnabled - Array of objects describing enabled render nodes.
 * @param {boolean} useAll - Use all render nodes?
 * @param {callback} onSelectAll - Function to call if select all is clicked
 * @param {callback} onSelectNone - Function to call if select none is clicked
 * @param {callback} onCheckNode - Function to call if node button is checked
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
          var isChecked = false;
          if (props.renderNodes.includes(name) && props.nodesEnabled.includes(name)) {
            isChecked = true;
          };
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
 * @param {function} onSubmit - Called when input is submitted.
 * @param {str} path - Initial path to set in browser.
 * @param {int} startFrame - Optional: Value to set in start frame field.
 * @param {int} endFrame - Optional: Value to set in end frame field.
 * @param {Object<string, boolean>} renderNodes - {nodeName: isEnabled, ... }
 */
class JobInput extends Component {
  constructor(props) {
    super(props);
    this.state = {
      path: props.path || '',
      startFrame: props.startFrame || '',
      endFrame: props.endFrame || '',
      renderNodes: [], // Represents *all* render nodes configured on server
      nodesEnabled: props.nodesEnabled || [], // Only those previously enabled on this job (for duplicating jobs)
      showBrowser: false,
      useAllNodes: (props.useAllNodes === undefined) ? true : props.useAllNodes,
    }
    this.toggleBrowser = this.toggleBrowser.bind(this);
    this.setPath = this.setPath.bind(this);
    this.selectAllNodes = this.selectAllNodes.bind(this);
    this.deselectAllNodes = this.deselectAllNodes.bind(this);
    this.setNodeState = this.setNodeState.bind(this);
    this.handleChange = this.handleChange.bind(this);
    this.submit = this.submit.bind(this);
  }

  componentDidMount() {
    if (this.state.renderNodes.length === 0) {
      axios.get(process.env.REACT_APP_BACKEND_API + "/node/list")
        .then(
          (result) => {return this.setState({renderNodes: Array.from(result.data)})},
          (error) => {console.log(error)},
        )
    }
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
    this.setState(state => {
      return {
        nodesEnabled: this.state.renderNodes,
        useAllNodes: true,
      }
    });
  }

  deselectAllNodes() {
    this.setState(state => {
      return {
        nodesEnabled: [],
        useAllNodes: false,
      }
    });
  }

  setNodeState(node) {
      const nodesEnabled = this.state.nodesEnabled;
      var i;
      i = nodesEnabled.indexOf(node);
      if (i >= 0) {
        nodesEnabled.delete(i);
      } else {
        nodesEnabled.push(node);
      };
      return this.setState({nodesEnabled: nodesEnabled});
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
    };

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
