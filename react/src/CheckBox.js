import React from 'react';

function CheckBox(props) {
  return (
    <div className={props.className}>
      <label>
        {props.label}
        <input
          type="checkbox"
          className={props.className}
          name={props.label}
          checked={props.checked}
          onChange={props.onChange}
        />
      </label>
    </div>
  )
}


export default CheckBox;
