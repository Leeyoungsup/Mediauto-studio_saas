/**
 * NDP.view2 색 매칭 보정 (Hamamatsu 전용, 클라이언트 사이드).
 *
 * color_match_analysis.ipynb 에서 MeDIAuto Studio 타일 (서버가 이미
 * γ=1.8 / white=235 으로 preprocess 한 결과) 을 NDP.view2 출력과
 * 픽셀 쌍 피팅한 결과. RMSE 4.21.
 *
 * 파이프라인:  stored_pixel  →  gamma(γ, white)  →  affine 3x3 + bias
 *              → NDP-matched pixel
 *
 * 뷰어의 toggle 로 ON/OFF 된다. 서버에 저장된 타일은 변경하지 않고
 * 브라우저가 받은 JPEG 픽셀에 추가 보정을 얹는다.
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

// ── gamma LUT 256-entry (1회 생성) ──
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

// ── 행렬 계수 전개 (타이트 루프 최적화) ──
// out[j] = sum_i(in[i] * M[i,j]) + bias[j]
const M00 = NDP_FIT.matrix[0][0], M01 = NDP_FIT.matrix[0][1], M02 = NDP_FIT.matrix[0][2];
const M10 = NDP_FIT.matrix[1][0], M11 = NDP_FIT.matrix[1][1], M12 = NDP_FIT.matrix[1][2];
const M20 = NDP_FIT.matrix[2][0], M21 = NDP_FIT.matrix[2][1], M22 = NDP_FIT.matrix[2][2];
const B0 = NDP_FIT.bias[0], B1 = NDP_FIT.bias[1], B2 = NDP_FIT.bias[2];

/**
 * ImageData 에 in-place γ + affine 보정.
 * Uint8ClampedArray 는 대입 시 자동 clamp 되므로 명시적 clip 불필요.
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
        // alpha (d[i+3]) 유지
    }
    return imageData;
}

/**
 * HTMLImageElement / HTMLCanvasElement / ImageBitmap 을 받아 보정된
 * HTMLCanvasElement 반환. `ctx.drawImage` 의 source 로 그대로 사용 가능.
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
