import React, { Component } from 'react';
import './JobInput.css';
import axios from "axios";
import { FileBrowserPopup } from './FileBrowser';

const RENDER_ENGINES = ["blend", "tgd"]


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
        {Object.keys(props.renderNodes).map(name => {
          return (
              <NodeBox
                key={name}
                name={name}
                checked={props.renderNodes[name]}
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
      renderEngine: props.renderEngine,
      renderNodes: props.renderNodes || {},
      showBrowser: false,
      useAllNodes: props.useAllNodes || true,
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
    if (Object.keys(this.state.renderNodes).length === 0) {
      this.getRenderNodes();
    }
  }

  getRenderNodes() {
    axios.get(process.env.REACT_APP_BACKEND_API + "/node/list")
      .then(
        (result) => {
          let renderNodes = {}
          for (var i = 0; i < result.data.length; i++) {
            renderNodes[result.data[i]] = false;
          }
          return this.setState({renderNodes: renderNodes})
        },
        (error) => {console.log(error)
      }
    )
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
      let newNodes = state.renderNodes;
      for (var name in newNodes) {
        newNodes[name] = true;
      }
      return {
        renderNodes: newNodes,
        useAllNodes: true,
      }
    });
  }

  deselectAllNodes() {
    this.setState(state => {
      let newNodes = state.renderNodes;
      for (var name in newNodes) {
        newNodes[name] = false;
      }
      return {
        renderNodes: newNodes,
        useAllNodes: false,
      }
    });
  }

  setNodeState(name) {
    this.setState(state => {
      let newNodes = state.renderNodes;
      newNodes[name] = !state.renderNodes[name];
      return {renderNodes: newNodes}
    });
  }

  handleChange(event) {
    this.setState({[event.target.name]: event.target.value});
  }

  submit() {
    const { path, startFrame, endFrame, renderNodes, useAllNodes } = this.state;

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
    for (var node in renderNodes) {
      if (useAllNodes || renderNodes[node]) {
        selectedNodes.push(node)
      }
    };

    const ret = {
      path: this.state.path,
      start_frame: this.state.startFrame,
      end_frame: this.state.endFrame,
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
