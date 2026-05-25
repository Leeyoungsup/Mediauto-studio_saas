/**
 * NDP.view2 text text text (Hamamatsu text, text text).
 *
 * color_match_analysis.ipynb text MeDIAuto Studio text (text text
 * γ=1.8 / white=235 text preprocess text text) text NDP.view2 text
 * text text text text. RMSE 4.21.
 *
 * text:  stored_pixel  →  gamma(γ, white)  →  affine 3x3 + bias
 *              → NDP-matched pixel
 *
 * text toggle text ON/OFF text. text text text text text
 * text text JPEG text text text text.
 */

export const NDP_FIT = Object.freeze({
    gamma: 1.094,
    white: 247.91,
    // row = input channel (R/G/B), col = output channel (R/G/B)
    matrix: [
        [ 1.3986, -0.1898,  0.0633],
        [ 0.0432,  1.1274, -0.034 ],
        [-0.449,  -0.0141,  0.8625],
    ],
    bias: [2.0654, 19.8732, 24.7427],
});

// ── gamma LUT 256-entry (1text text) ──
const _GAMMA_LUT = (() => {
    const lut = new Uint8ClampedArray(256);
    const float_w = NDP_FIT.white;
    const float_inv_g = 1.0 / NDP_FIT.gamma;
    for (let i = 0; i < 256; i++) {
        const float_x = Math.min(1.0, i / float_w);
        lut[i] = Math.round(255 * Math.pow(float_x, float_inv_g));
    }
    return lut;
})();

// ── text text text (text text text) ──
// out[j] = sum_i(in[i] * M[i,j]) + bias[j]
const M00 = NDP_FIT.matrix[0][0], M01 = NDP_FIT.matrix[0][1], M02 = NDP_FIT.matrix[0][2];
const M10 = NDP_FIT.matrix[1][0], M11 = NDP_FIT.matrix[1][1], M12 = NDP_FIT.matrix[1][2];
const M20 = NDP_FIT.matrix[2][0], M21 = NDP_FIT.matrix[2][1], M22 = NDP_FIT.matrix[2][2];
const B0 = NDP_FIT.bias[0], B1 = NDP_FIT.bias[1], B2 = NDP_FIT.bias[2];

/**
 * ImageData text in-place γ + affine text.
 * Uint8ClampedArray text text text text clamp text text clip text.
 */
export function applyNdpFitToImageData(imageData) {
    const d = imageData.data;
    const lut = _GAMMA_LUT;
    const int_len = d.length;
    for (let i = 0; i < int_len; i += 4) {
        const r = lut[d[i]];
        const g = lut[d[i + 1]];
        const b = lut[d[i + 2]];
        d[i]     = r * M00 + g * M10 + b * M20 + B0;
        d[i + 1] = r * M01 + g * M11 + b * M21 + B1;
        d[i + 2] = r * M02 + g * M12 + b * M22 + B2;
        // alpha (d[i+3]) text
    }
    return imageData;
}

/**
 * HTMLImageElement / HTMLCanvasElement / ImageBitmap text text text
 * HTMLCanvasElement text. `ctx.drawImage` text source text text text text.
 *
 * @param {CanvasImageSource} src
 * @returns {HTMLCanvasElement}
 */
export function colorCorrectBitmap(src) {
    const int_w = src.naturalWidth || src.width || 0;
    const int_h = src.naturalHeight || src.height || 0;
    if (int_w <= 0 || int_h <= 0) return null;

    const canvas = document.createElement('canvas');
    canvas.width = int_w;
    canvas.height = int_h;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(src, 0, 0);
    const imgData = ctx.getImageData(0, 0, int_w, int_h);
    applyNdpFitToImageData(imgData);
    ctx.putImageData(imgData, 0, 0);
    return canvas;
}
