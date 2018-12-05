import React, { Component } from 'react';
import axios from "axios";
import './JobInput.css';
import FileBrowser from './FileBrowser';
import CheckBox from './CheckBox';

const RENDER_ENGINES = ["blend", "tgd"]

/**
 * Displays FileBrowser in a popup overlay.
 */
function BrowserPopup(props) {
  return (
    <div className="browser-overlay" >
      <div className="browser-inner">
        <ul>
          <li className="layout-row">
            <p className="right" onClick={props.onClose}>X</p>
          </li>
          <li className="layout-row">
            <FileBrowser
              url={props.url}
              path={props.path}
              onFileClick={props.onFileClick}
            />
          </li>
        </ul>
      </div>
    </div>
  )
}


/**
 * Number input field that changes CSS className if value contains a non-digit.
 * @param {str} name: Name attribute of HTML input
 * @param {int} value: Contents of input field.
 * @param {function} onChange - Callback on input change.
 */
class NumberInput extends Component {
  constructor(props) {
    super(props);
    this.classNameOk = "number-input";
    this.classNameBad = "number-input-bad";
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
      <label>
        Input:
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
 * Widget for selecting render nodes.
 * @param {Array} renderNodes - Array of objects describing render nodes.
 */
function NodePicker(props) {
  return (
    <ul>
      <li className="layout-row">Render nodes</li>
      <li className="layout-row">
        <div className="left"><p className="text-link" onClick={props.onSelectAll}>Select All</p></div>
        <div className="left"><p className="text-link" onClick={props.onSelectNone}>Select None</p></div>
      </li>
      <li className="layout-row">
        {Object.keys(props.renderNodes).map(name => {
          return (
              <CheckBox
                key={name}
                label={name}
                checked={props.renderNodes[name]}
                className="left"
                onChange={props.onCheckNode}
              />
          )
        })}
      </li>
    </ul>
  )
}


/**
 * Job input widget.
 * @param {function} onSubmit - Called when input is submitted.
 * @param {str} url - URL of API
 * @param {str} path - Initial path to set in browser.
 * @param {int} startFrame - Optional: Value to set in start frame field.
 * @param {int} endFrame - Optional: Value to set in end frame field.
 * @param {Object<string, boolean>} renderNodes - {nodeName: isEnabled, ... }
 */
class JobInput extends Component {
  constructor(props) {
    super(props);
    this.state = {
      path: props.path,
      startFrame: props.startFrame ? undefined: '',
      endFrame: props.endFrame ? undefined: '',
      renderEngine: props.renderEngine,
      renderNodes: props.renderNodes,
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
    this.setState(state => {
      let newNodes = state.renderNodes;
      for (var name in newNodes) {
        newNodes[name] = true;
      }
      console.log(newNodes)
      return {renderNodes: newNodes}
    });
  }

  deselectAllNodes() {
    this.setState(state => {
      let newNodes = state.renderNodes;
      for (var name in newNodes) {
        newNodes[name] = false;
      }
      console.log(newNodes)
      return {renderNodes: newNodes}
    });
  }

  setNodeState(event) {
    const name = event.target.name;
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
    const path = this.state.path;
    const startFrame = this.state.startFrame;
    const endFrame = this.state.endFrame;
    const renderNodes = this.state.renderNodes;
    console.log(path, startFrame, endFrame, renderNodes)


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
      if (renderNodes[node])
        selectedNodes.push(node)
    };

    // Determine render engine based on file extension.
    // TODO Might be better to do this on the render server.
    const pathArray = path.split('.');
    const ext = pathArray[pathArray.length - 1];
    console.log(ext)
    if (!RENDER_ENGINES.includes(ext)) {
      // FIXME: handle this correctly.
      alert('Project file name must end with ".blend" or ".tgd"')
      return;
    }
    const ret = {
      path: this.state.path,
      start_frame: this.state.startFrame,
      end_frame: this.state.endFrame,
      render_engine: ext,
      nodes: selectedNodes
    }
    console.log(ret);
    axios.post(this.props.url + "/job/new", ret)
      .then((result) => {console.log(result)}, (error) => console.error(error))
    this.props.onClose();
  }

  render() {
    return (
      <div className="input-container">
        {this.state.showBrowser &&
          <BrowserPopup
            url={this.props.url + "/storage/ls"}
            path={this.props.path}
            onClose={this.toggleBrowser}
            onFileClick={this.setPath}
          />
        }
        <ul>
          <li className="layout-row">
            <label>
              Path:
              <input type="text" name="path" value={this.state.path} onChange={this.handleChange} />
              <input type="button" value="Browse" onClick={this.toggleBrowser} />
            </label>
          </li>
          <li className="layout-row">
            <NumberInput name="startFrame" value={this.state.startFrame} onChange={this.handleChange} />
            <NumberInput name="endFrame" value={this.state.endFrame} onChange={this.handleChange} />
          </li>
          <li className="layout-row">
            <NodePicker
              renderNodes={this.props.renderNodes}
              onCheckNode={this.setNodeState}
              onSelectAll={this.selectAllNodes}
              onSelectNone={this.deselectAllNodes}
            />
          </li>
          <li className="layout-row">
            <div className="left"><button onClick={this.submit} >OK</button></div>
            <div className="left"><button onClick={this.props.onClose} >Cancel</button></div>
          </li>
          <li className="layout-row"><br />Check:<br />Path: "{this.state.path}"<br />Start: {this.state.startFrame} End: {this.state.endFrame}<br />
          Nodes: {Object.keys(this.state.renderNodes).map(node => " " + node + ": " + this.state.renderNodes[node].toString())}</li>
        </ul>
      </div>
    )
  }
}



class Wrapper extends Component {
  constructor(props) {
    super(props);
    this.state = {
      isOpen: true,
    }
  }

  closeWin() {
    this.setState({isOpen: false})
  }

  render() {
    //const testNodes = [{name: "node1", enabled:true}, {name: "node2", enabled: false}]
    //const testNodes = {node1: {enabled: true, rendering: false}, node2: {enabled: false, rendering: false}}
    const testNodes = {grob4: false, borg5: false, borg3: false, grob2: false, grob6: false, eldiente: false, borg2: false, hex2: false, paradox: false, hex1: false}
    if (this.state.isOpen) {
      return <JobInput path="/" url={"http://localhost:2020"} renderNodes={testNodes} onClose={() => this.closeWin()}/>
    }
    return <p>Closed</p>
  }
}

export default JobInput;
