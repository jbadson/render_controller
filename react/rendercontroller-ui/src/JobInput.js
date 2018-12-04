import React, { Component } from "react";
import "./JobInput.css";
import FileBrowser from './FileBrowser';
import CheckBox from './CheckBox';

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
                checked={props.renderNodes[name].enabled}
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
        newNodes[name]["enabled"] = true;
      }
      console.log(newNodes)
      return {renderNodes: newNodes}
    });
  }

  deselectAllNodes() {
    this.setState(state => {
      let newNodes = state.renderNodes;
      for (var name in newNodes) {
        newNodes[name]["enabled"] = false;
      }
      console.log(newNodes)
      return {renderNodes: newNodes}
    });
  }

  setNodeState(event) {
    const name = event.target.name;
    this.setState(state => {
      let newNodes = state.renderNodes;
      newNodes[name]["enabled"] = !state.renderNodes[name]["enabled"];
      return {renderNodes: newNodes}
    });
  }

  handleChange(event) {
    this.setState({[event.target.name]: event.target.value});
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
        <form>
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
              Render nodes
              <NodePicker
                renderNodes={this.props.renderNodes}
                onCheckNode={this.setNodeState}
                onSelectAll={this.selectAllNodes}
                onSelectNone={this.deselectAllNodes}
              />
            </li>
            <li className="layout-row">
              //FIXME Buttons are causing the page to refresh for some reason.
              <div className="left"><button>OK</button></div>
              <div className="left"><button>Cancel</button></div>
            </li>
            <li className="layout-row"><br />Check:<br />Path: "{this.state.path}"<br />Start: {this.state.startFrame} End: {this.state.endFrame}<br />
            Nodes: {Object.keys(this.state.renderNodes).map(node => " " + node + ": " + this.state.renderNodes[node]["enabled"].toString())}</li>
          </ul>
        </form>
      </div>
    )
  }
}



class Wrapper extends Component {
  render() {
    //const testNodes = [{name: "node1", enabled:true}, {name: "node2", enabled: false}]
    const testNodes = {node1: {enabled: true, rendering: false}, node2: {enabled: false, rendering: false}}
    return <JobInput path="/" url={"http://localhost:2020"} renderNodes={testNodes} />
  }
}

export default Wrapper;
