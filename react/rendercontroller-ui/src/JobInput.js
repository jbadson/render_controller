import React, { Component } from "react";
import "./JobInput.css";
import FileBrowser from './FileBrowser';


/**
 * Job input widget.
 * @param {function} onSubmit - Called when input is submitted.
 */
class JobInput extends Component {
  constructor(props) {
    super(props);
    this.state = {
      path: props.path,
      startFrame: props.startFrame,
      endFrame: props.endFrame,
      renderEngine: props.renderEngine,
      renderNodes: props.renderNodes,
    }
  }
  render() {
    return (
      <div>
        <ul>
          <li>Path:</li>
          <li>Start frame: End frame:</li>
          <li>Render nodes</li>
          <li>OK, Cancel</li>
        </ul>
      </div>
    )
  }
}
